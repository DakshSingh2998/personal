
import discord
from discord.ext import commands

import asyncio
import itertools
import sys
import traceback
from async_timeout import timeout
from functools import partial
from youtube_dl import YoutubeDL


timeestamp=0
ytdlopts = {
    'format': 'bestaudio/best',
    'outtmpl': 'downloads/%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'extract_audio':True,
    'source_address': '0.0.0.0',# ipv6 addresses cause issues sometimes
    
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '4',
    }],
    
    'skip_download':True,
    
    
    
}
sflag=0



ytdl = YoutubeDL(ytdlopts)


class VoiceConnectionError(commands.CommandError):
    """Custom Exception class for connection errors."""


class InvalidVoiceChannel(VoiceConnectionError):
    """Exception for cases of invalid Voice Channels."""


class YTDLSource(discord.PCMVolumeTransformer):

    def __init__(self, source, *, data, requester):
        super().__init__(source)
        self.requester = requester

        self.title = data.get('title')
        self.webpage_url = data.get('webpage_url')

        # YTDL info dicts (data) have other useful information you might want
        # https://github.com/rg3/youtube-dl/blob/master/README.md

    def __getitem__(self, item: str):
        return self.__getattribute__(item)

    @classmethod
    async def create_source(cls, ctx, search: str, *, loop, download=False):
        loop = loop or asyncio.get_event_loop()

        to_run = partial(ytdl.extract_info, url=search, download=download)
        data = await loop.run_in_executor(None, to_run)

        if 'entries' in data:
            # take first item from a playlist
            data = data['entries'][0]
            global timeestamp
        
        ffmpegopts = {
        'before_options': f'-vn -nostdin -ss {timeestamp} -threads 12 -probesize 32 -analyzeduration 0 -fflags nobuffer -thread_queue_size 10000' ,
        'options': f'-vn -preset ultrafast -ab 64 -tune zerolatency'
        }

        if download:
            source = ytdl.prepare_filename(data)
        else:
            return {'webpage_url': data['webpage_url'], 'requester': ctx.author, 'title': data['title']}


        return cls(discord.FFmpegPCMAudio(source,**ffmpegopts), data=data, requester=ctx.author)

    @classmethod
    async def regather_stream(cls, data, *, loop):
        loop = loop or asyncio.get_event_loop()
        requester = data['requester']

        to_run = partial(ytdl.extract_info, url=data['webpage_url'], download=False)
        data = await loop.run_in_executor(None, to_run)
        global timeestamp
        ffmpegopts = {
        'before_options': f'-vn -nostdin -ss {timeestamp} -threads 12 -probesize 32 -analyzeduration 0 -fflags nobuffer -thread_queue_size 10000' ,
        'options': '-vn -preset ultrafast -ab 64 -tune zerolatency'
        }

        return cls(discord.FFmpegPCMAudio(data['url'],**ffmpegopts), data=data, requester=requester)


class MusicPlayer:

    __slots__ = ('bot', '_guild', '_channel', '_cog', 'queue', 'next', 'current', 'np', 'volume','que','embed','nowp','searchqueue')

    def __init__(self, ctx):
        self.bot = ctx.bot
        self._guild = ctx.guild
        self._channel = ctx.channel
        self._cog = ctx.cog

        self.queue = asyncio.Queue()
        self.next = asyncio.Event()

        self.np = None  # Now playing message
        self.que=None
        self.embed=None
        self.volume = 1.0
        self.current = None
        self.nowp=None
        self.searchqueue=asyncio.Queue()

        ctx.bot.loop.create_task(self.player_loop(ctx))

    async def showw(self,ctx):
        try:
        # Grab up to 5 entries from the queue...
            vc = ctx.voice_client

            if not vc or not vc.is_connected():
                return #await ctx.send('I am not currently connected to voice!',delete_after=10)
            
            upcoming = list(itertools.islice(self.queue._queue, 0, 999999))
            ii=0
            #fmt = '\n'.join(f'{_["title"]}' for _ in upcoming)
            fmt=''
            for temp in upcoming:
                tt=temp["title"]
                ii=ii+1
                fmt=fmt+f'{ii}. {temp["title"]}\n'
                #print(temp)
                #print("##########")
                
            #self.embed = discord.Embed(title=f'Upcoming - Next {len(upcoming)}', description=fmt)
            #self.embed=await self._channel.send(f'Upcoming - Next {len(upcoming)}\n{fmt}')
            try:
                await self.que.delete()
                await self.np.delete()
            except Exception as e:
                #print("EEE",e)
                yy=5

            self.que=await self._channel.send(f'Upcoming - Next {len(upcoming)}\n{fmt}')
            self.np = await self._channel.send(f'Requested by @{vc.source.requester} {vc.source.webpage_url}')
        except Exception as e:
            await self._channel.send(f'NO songs in queue: {e}',delete_after=10)
            
            
            
            
            
    async def seek(self,ctx):
        #print(self.nowp)
        try:
            # Grab up to 5 entries from the queue...
            vc = ctx.voice_client

            if not vc or not vc.is_connected():
                return #await ctx.send('I am not currently connected to voice!',delete_after=10)
            

            ssource = await YTDLSource.create_source(ctx, self.nowp, loop=self.bot.loop, download=False)
            #print(ssource)
            tsize=0
            #print(self.queue)
            #print('--')
            temp=asyncio.Queue()
            temp2=asyncio.Queue()
            tsize=self.queue.qsize()
            while(tsize>0):
                t=await self.queue.get()
                t2=await self.searchqueue.get()
                await temp2.put(t2)
                await temp.put(t)
                tsize=tsize-1
            self.queue=None
            self.queue = asyncio.Queue()
            self.searchqueue=None
            self.searchqueue = asyncio.Queue()
            await self.queue.put(ssource)
            await self.searchqueue.put(self.nowp)
            tsize=temp.qsize()
            while(tsize>0):
                t=await temp.get()
                t2=await temp2.get()
                await self.searchqueue.put(t2)
                await self.queue.put(t)
                tsize=tsize-1
                
            yy=5
            #print(self.queue)
            await self.np.delete()
            await self.que.delete()


            

            
        except Exception as e:
            print(e)
        
        
    async def player_loop(self,ctx):
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            self.next.clear()

            try:
                async with timeout(99999999):  # 5 minutes...
                    source = await self.queue.get()
                    ssearch=await self.searchqueue.get()
                    self.nowp=ssearch
            except asyncio.TimeoutError:
                return self.destroy(self._guild)

            if not isinstance(source, YTDLSource):
                # Source was probably a stream (not downloaded)
                # So we should regather to prevent stream expiration
                try:
                    source = await YTDLSource.regather_stream(source, loop=self.bot.loop)
                    
                except Exception as e:
                    await self._channel.send(f'There was an error processing your song.\n'
                                             f'```css\n[{e}]\n```',delete_after=10)
                    continue

            source.volume = self.volume
            self.current = source

            self._guild.voice_client.play(source, after=lambda _: self.bot.loop.call_soon_threadsafe(self.next.set))
            await self.showw(ctx)
            
            
            await self.next.wait()
            global sflag
            if sflag==0:
                global timeestamp
                timeestamp=0
            else:
                sflag=0
            source.cleanup()
            self.current = None

            try:
                await self.que.delete()
                await self.np.delete()
            except discord.HTTPException:
                pass

    def destroy(self, guild):
        return self.bot.loop.create_task(self._cog.cleanup(guild))


class Music(commands.Cog):

    __slots__ = ('bot', 'players')

    def __init__(self, bot):
        self.bot = bot
        self.players = {}

        

    async def cleanup(self, guild):
        try:
            await guild.voice_client.disconnect()
        except AttributeError:
            pass

        try:
            del self.players[guild.id]
        except KeyError:
            pass

    async def __local_check(self, ctx):
        if not ctx.guild:
            raise commands.NoPrivateMessage
        return True

    async def __error(self, ctx, error):
        if isinstance(error, commands.NoPrivateMessage):
            try:
                return await ctx.send('This command can not be used in Private Messages.',delete_after=10)
            except discord.HTTPException:
                pass
        elif isinstance(error, InvalidVoiceChannel):
            await ctx.send('Error connecting to Voice Channel. '
                           'Please make sure you are in a valid channel or provide me with one',delete_after=10)

        print('Ignoring exception in command {}:'.format(ctx.command), file=sys.stderr)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

    def get_player(self, ctx):
        try:
            player = self.players[ctx.guild.id]
        except KeyError:
            player = MusicPlayer(ctx)
            self.players[ctx.guild.id] = player

        return player
    

    @commands.command(name='connect', aliases=['join'])
    async def connect_(self, ctx, *, channel: discord.VoiceChannel=None):
        if not channel:
            try:
                channel = ctx.author.voice.channel
            except AttributeError:
                raise InvalidVoiceChannel('No channel to join. Please either specify a valid channel or join one.')

        vc = ctx.voice_client

        if vc:
            if vc.channel.id == channel.id:
                return
            try:
                await vc.move_to(channel)
            except asyncio.TimeoutError:
                raise VoiceConnectionError(f'Moving to channel: <{channel}> timed out.',delete_after=10)
        else:
            try:
                await channel.connect()
            except asyncio.TimeoutError:
                raise VoiceConnectionError(f'Connecting to channel: <{channel}> timed out.',delete_after=10)

        await ctx.send(f'Connected to: **{channel}**', delete_after=10)
        await ctx.message.delete()
        

    @commands.command(name='play', aliases=['sing','p'])
    async def play_(self, ctx, *, search: str):
        await ctx.trigger_typing()

        vc = ctx.voice_client

        if not vc:
            await ctx.invoke(self.connect_)

        player = self.get_player(ctx)
        

        source = await YTDLSource.create_source(ctx, search, loop=self.bot.loop, download=False)

        await player.queue.put(source)
        await player.searchqueue.put(search)
        await self.now_playing_(ctx)
        try:
            await ctx.message.delete()
        except Exception as e:
            print(e)
        yy=5
    @commands.command(name='resume', aliases=['r','res'])
    async def resume_(self, ctx):
        vc = ctx.voice_client

        if not vc or not vc.is_connected():
            return #await ctx.send('I am not currently playing anything!', delete_after=10)
        elif not vc.is_paused():
            return

        vc.resume()
        await ctx.send(f'**`{ctx.author}`**: Resumed the song!',delete_after=10)
        await ctx.message.delete()
        



    @commands.command(name='skip')
    async def skip_(self, ctx):
        vc = ctx.voice_client

        if not vc or not vc.is_connected():
            return #await ctx.send('I am not currently playing anything!', delete_after=10)

        if vc.is_paused():
            pass
        elif not vc.is_playing():
            return
        try:
            player=self.get_player(ctx)
            await player.np.delete()
            await player.que.delete()
            await ctx.message.delete()
        except Exception as e:
            print("skip",e)
        vc.stop()
        await ctx.send(f'**`{ctx.author}`**: Skipped the song!',delete_after=10)
        


    @commands.command(name='queue_info', aliases=['q', 'playlist','queue'])
    async def queue_info(self, ctx):
        player = self.get_player(ctx)
        await player.showw(ctx)
        await ctx.message.delete()
        


    @commands.command(name='now_playing', aliases=['np', 'current', 'currentsong', 'playing'])
    async def now_playing_(self, ctx):

        player = self.get_player(ctx)
        if not player.current:
            return #await ctx.send('I am not currently playing anything!',delete_after=10)
        await player.showw(ctx)
        try:
            await ctx.message.delete()
        except Exception as e:
            print(e)
        yy=5
        

    @commands.command(name='change_volume', aliases=['vol','volume'])
    async def change_volume(self, ctx, *, vol: float):
        
        vc = ctx.voice_client

        if not vc or not vc.is_connected():
            return #await ctx.send('I am not currently connected to voice!', delete_after=10)

        if not 0 < vol < 101:
            return await ctx.send('Please enter a value between 1 and 100.',delete_after=10)

        player = self.get_player(ctx)

        if vc.source:
            vc.source.volume = vol / 100

        player.volume = vol / 100
        await ctx.send(f'**`{ctx.author}`**: Set the volume to **{vol}%**',delete_after=10)
        await ctx.message.delete()
        


    @commands.command(name='stop')
    async def stop_(self, ctx):
        vc = ctx.voice_client

        if not vc or not vc.is_connected():
            return #await ctx.send('I am not currently playing anything!', delete_after=10)
        try:
            player=self.get_player(ctx)
            await player.np.delete()
            await player.que.delete()
            await ctx.message.delete()
        except Exception as e:
            print("stop",e)

        await self.cleanup(ctx.guild)
        

        

    @commands.command(name='seek')
    async def seek_(self, ctx, *, search: int):
        global sflag
        sflag=1
        player=self.get_player(ctx)
        await player.seek(ctx)
        vc = ctx.voice_client
        
        global timeestamp
        #print(timeestamp)
        timeestamp=search
        #print(timeestamp)
        if not vc or not vc.is_connected():
            return #await ctx.send('I am not currently playing anything!', delete_after=10)
        
        vc.stop()


    @commands.command(name="pause", aliases=["pausee"])
    async def pause_(self, ctx):
        vc = ctx.voice_client

        if not vc or not vc.is_playing():
            return #await ctx.send('I am not currently playing anything!', delete_after=10)
        elif vc.is_paused():
            return

        vc.pause()
        await ctx.send(f'**`{ctx.author}`**: Paused the song!',delete_after=10)
        await ctx.message.delete()
        


    @commands.command(name='remove', aliases=['rem'])
    async def remove_(self, ctx,*,index:int):
        vc = ctx.voice_client

        if not vc or not vc.is_playing():
            return #await ctx.send('I am not currently playing anything!', delete_after=10)
        elif vc.is_paused():
            return

        player=self.get_player(ctx)
        try:
            tsize=0
            temp=asyncio.Queue()
            temp2=asyncio.Queue()
            tsize=player.queue.qsize()
            while(tsize>0):
                t=await player.queue.get()
                t2=await player.searchqueue.get()
                await temp2.put(t2)
                await temp.put(t)
                tsize=tsize-1
            player.queue=None
            player.queue = asyncio.Queue()
            player.searchqueue=None
            player.searchqueue = asyncio.Queue()
            tsize=temp.qsize()
            tflag=1
            while(tsize>0):
                if tflag!=index:
                    t=await temp.get()
                    t2=await temp2.get()
                    await player.searchqueue.put(t2)
                    await player.queue.put(t)
                else:
                    await temp.get()
                    await temp2.get()
                tsize=tsize-1
                tflag=tflag+1
            yy=5
        except Exception as e:
            yy=5
        await player.showw(ctx)
        
        await ctx.send(f'**`{ctx.author}`**: Removed the song!',delete_after=40)
        await ctx.message.delete()
            
            

def setup(bot):
    bot.add_cog(Music(bot))