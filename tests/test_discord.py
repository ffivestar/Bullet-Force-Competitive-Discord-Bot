import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord
from bot import BFCBot
from cogs.tournaments import BoardView, ConfirmView, ResultModal, TournamentCog, permitted
from config import Settings
from database import Database
from discord_channels import MatchChannelManager
from store import Store
from rendering import bracket_png
from test_engine import tournament, play
import engine


def settings(path):
    return Settings('test-token',path,None,'BFC Tournaments','match-results','Tournament Staff','BFC Admin',True)


class DiscordTests(unittest.IsolatedAsyncioTestCase):
    async def test_extensions_commands_and_views(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Database(Path(tmp)/'test.sqlite3');db.connect()
            bot=BFCBot(settings(db.path),db)
            async with bot:
                await bot.load_extension('cogs.general')
                await bot.load_extension('cogs.tournaments')
                cog=bot.get_cog('TournamentCog')
                groups={c.name:c for c in bot.tree.get_commands()}
                self.assertEqual(set(groups),{'ping','tournament','players','teams','team','match','stats'})
                self.assertEqual({c.name for c in groups['match'].commands},{'view','result','undo','history','settings'})
                # Serialize exactly what would be sent to Discord during slash-command sync.
                for command in bot.tree.get_commands():
                    command.to_dict(bot.tree)
                t=tournament(4);engine.start(t)
                mid=next(k for k,m in t['matches'].items() if m['status']=='ready')
                modal=ResultModal(cog,t,mid)
                self.assertEqual(len(modal.children),3)
                self.assertTrue(BoardView(cog,1).is_persistent())
                self.assertEqual(len(ConfirmView(cog,1,mid,1,0,[3,1],{}).children),2)
            db.close()

    async def test_runtime_permissions(self):
        member=MagicMock(spec=discord.Member)
        member.guild_permissions=SimpleNamespace(administrator=False)
        member.roles=[]
        cfg=settings(Path('unused'))
        self.assertFalse(permitted(member,cfg))
        member.roles=[SimpleNamespace(name='Tournament Staff')]
        self.assertTrue(permitted(member,cfg))
        self.assertFalse(permitted(member,cfg,admin=True))
        member.roles=[SimpleNamespace(name='BFC Admin')]
        self.assertTrue(permitted(member,cfg,admin=True))
        member.roles=[]; member.guild_permissions.administrator=True
        self.assertTrue(permitted(member,cfg,admin=True))

    async def test_private_voice_and_recovery(self):
        t=tournament(2);engine.start(t)
        guild=MagicMock()
        guild.id=123
        guild.default_role=object(); guild.me=object()
        staff=SimpleNamespace(name='Tournament Staff')
        # Role/member objects need to be hashable for overwrite maps.
        staff=MagicMock(); staff.name='Tournament Staff'
        admin=MagicMock(); admin.name='BFC Admin'
        guild.roles=[staff,admin]
        category=MagicMock();category.name='BFC Tournaments 1 · 1';category.channels=[]
        guild.categories=[category]; guild.channels=[]
        members={int(uid):object() for uid in t['players']}
        guild.get_member.side_effect=members.get
        created={}
        sequence=iter(range(100,110))
        async def create(name,**kwargs):
            cid=next(sequence)
            channel=MagicMock();channel.id=cid;channel.name=name
            channel.send=AsyncMock(return_value=SimpleNamespace(id=1000+cid))
            created[cid]=(channel,kwargs['overwrites'])
            return channel
        guild.create_text_channel=AsyncMock(side_effect=create)
        guild.create_voice_channel=AsyncMock(side_effect=create)
        guild.get_channel.side_effect=lambda cid:created.get(cid,(None,))[0]
        bot=SimpleNamespace(settings=settings(Path('unused')))
        store=SimpleNamespace(save=MagicMock())
        manager=MatchChannelManager(bot,store)
        await manager.ensure_room(guild,t,t['matches']['W1'])
        room=t['rooms']['W1']
        a,b=t['matches']['W1']['teams']
        for key,tid,other in [('a',a,b),('b',b,a)]:
            overwrites=created[room[key]][1]
            self.assertFalse(overwrites[guild.default_role].view_channel)
            self.assertFalse(overwrites[guild.default_role].connect)
            self.assertTrue(overwrites[staff].connect)
            self.assertTrue(overwrites[admin].connect)
            for uid in t['teams'][tid]['players']:
                self.assertTrue(overwrites[members[int(uid)]].connect)
            for uid in t['teams'][other]['players']:
                self.assertNotIn(members[int(uid)],overwrites)
        text=created[room['text']][1]
        self.assertTrue(text[guild.default_role].view_channel)
        self.assertFalse(text[guild.default_role].send_messages)
        for uid in t['players']:
            self.assertTrue(text[members[int(uid)]].send_messages)
        await manager.ensure_room(guild,t,t['matches']['W1'])
        self.assertEqual(guild.create_text_channel.await_count,1)
        self.assertEqual(guild.create_voice_channel.await_count,2)

    async def test_cleanup_after_restart_and_archive_before_delete(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Database(Path(tmp)/'test.sqlite3');db.connect();store=Store(db)
            t=store.create(123,'Cleanup',1)
            source=tournament(2)
            t['teams'],t['players']=source['teams'],source['players']
            engine.start(t)
            t['rooms']['W1']={'text':10,'a':11,'b':12,'version':0}
            play(t,'W1')
            store.save(t)
            channels={cid:MagicMock() for cid in (10,11,12,20)}
            for cid,ch in channels.items():
                ch.id=cid;ch.send=AsyncMock(return_value=SimpleNamespace(id=200));ch.delete=AsyncMock()
            archive=channels[20]; archive.name='match-results'
            guild=MagicMock();guild.text_channels=[archive];guild.get_channel.side_effect=channels.get
            bot=SimpleNamespace(settings=settings(db.path),get_guild=lambda gid:guild)
            manager=MatchChannelManager(bot,store)
            manager.ensure_room=AsyncMock()
            await manager.sync(t)
            self.assertIn('W1',t['archives'])
            self.assertNotIn('W1',t['rooms'])
            self.assertEqual(len(t['cleanup']),1)
            channels[10].delete.assert_not_awaited()
            # Simulate restart and expiry of the durable cleanup deadline.
            db.close();db.connect();store=Store(db);manager.store=store
            restored=store.get(t['id'],123)
            with patch('discord_channels.time.time',return_value=restored['cleanup'][0]['after']+1):
                await manager.sync(restored)
            for cid in (10,11,12):
                channels[cid].delete.assert_awaited_once()
            self.assertEqual(restored['cleanup'],[])
            db.close()

    async def test_render_bracket_all_sizes(self):
        from PIL import Image
        for n in (2,3,8,17,32):
            t=tournament(n);engine.start(t)
            buf=bracket_png(t)
            image=Image.open(buf)
            self.assertEqual(image.format,'PNG')
            self.assertGreater(image.width,900)
            self.assertLess(len(buf.getvalue()),8_000_000)


if __name__=='__main__':
    unittest.main()
