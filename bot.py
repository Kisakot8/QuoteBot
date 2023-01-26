# ████████╗░█████╗░██████╗░
# ╚══██╔══╝██╔══██╗██╔══██╗
# ░░░██║░░░██║░░██║██████╔╝
# ░░░██║░░░██║░░██║██╔═══╝░
# ░░░██║░░░╚█████╔╝██║░░░░░
# ░░░╚═╝░░░░╚════╝░╚═╝░░░░░

# ================ LIBRARIES ================
import asyncio
import asyncpg
import datetime
import random
import discord
from discord.ext import commands
from discord.app_commands import Group
from typing import Literal, Optional
from discord.ext.commands import Greedy, Context

# ================ CONSTANTS ================

with open('secrets.txt','r',encoding='utf-8') as f:
    lines = f.readlines()
    for i in range(len(lines)):
        line = lines[i]
        lines[i] = line.strip("\n")
    TOKEN = lines[0]
    SQL_DSN = lines[1]
    CONSOLE = int(lines[2])

NEWLINE = '\n'
TIMEOUT = 40.0

# Colours taken from https://discord.com/branding
GREEN = 0x57F287
RED = 0xED4245
GRAY = 0x2F3136

# ================ INITIALISATION ================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents, owner_id=CONSOLE, help_command=None)

async def main():
    async with bot:
        async with asyncpg.create_pool(dsn=SQL_DSN,command_timeout=60) as pool:
            bot.pool = pool
            bot.loop.create_task(get_commands())
            await bot.start(TOKEN)


# ███████╗██╗░░░██╗███╗░░██╗░█████╗░████████╗██╗░█████╗░███╗░░██╗░██████╗
# ██╔════╝██║░░░██║████╗░██║██╔══██╗╚══██╔══╝██║██╔══██╗████╗░██║██╔════╝
# █████╗░░██║░░░██║██╔██╗██║██║░░╚═╝░░░██║░░░██║██║░░██║██╔██╗██║╚█████╗░
# ██╔══╝░░██║░░░██║██║╚████║██║░░██╗░░░██║░░░██║██║░░██║██║╚████║░╚═══██╗
# ██║░░░░░╚██████╔╝██║░╚███║╚█████╔╝░░░██║░░░██║╚█████╔╝██║░╚███║██████╔╝
# ╚═╝░░░░░░╚═════╝░╚═╝░░╚══╝░╚════╝░░░░╚═╝░░░╚═╝░╚════╝░╚═╝░░╚══╝╚═════╝░

@bot.event
async def on_guild_join(guild) -> None:
    '''
    Creates a table named quotes_(guild_id) when first joining a guild
    if such a table does not already exist.
    '''
    async with bot.pool.acquire() as con:
        await con.execute(f'''
        CREATE TABLE IF NOT EXISTS quotes_{guild.id} (
            true_id SERIAL PRIMARY KEY,
            text TEXT,
            authorid BIGINT,
            date DATE,
            url VARCHAR(255));
        ''')


async def get_commands() -> None:
    await bot.wait_until_ready()
    cmds = await bot.tree.sync()
    global cmd_info
    cmd_info = {cmd.name:(cmd.id, cmd.description) for cmd in cmds}
    cmd_info = dict(sorted(cmd_info.items()))
    return


async def clear_table(guild_id: int) -> None:
    async with bot.pool.acquire() as con:
        await con.execute(f'''
        TRUNCATE table quotes_{guild_id};
        ''')


async def make_quote_list(quotes_data: list, page: int, page_count: int, colour: int = 0x2F3136) -> discord.Embed:
    has_image_quote = False
    has_multiline_quote = False
    quotes_data = [[v for v in dict(record).values()] for record in quotes_data]
    quote_list = ''
    for row in quotes_data:
        row_is_multiline = False
        if row[5] != None:
            has_image_quote = True
        if '\n' in row[2]:
            has_multiline_quote = True
            row_is_multiline = True
            row[2] = f'{row[2].split(NEWLINE)[0]}...'
        quote_list += f'''{row[0]}. **❝{row[2]}❞** - <@{row[3]}>, {datetime.datetime.strptime(str(row[4]), '%Y-%m-%d').strftime('%d-%m-%Y')}{'' if row[5] is None else ', _has image_'}{'' if not row_is_multiline else ', _is multi-line_'}\n'''
    if has_image_quote or has_multiline_quote:
        quote_list += f'__**Note:**__ To view quotes containing multiple lines/images, do </quote:{cmd_info["quote"][0]}> <id>'
    embed = discord.Embed(title=f'Page {page}/{page_count}', description=quote_list, colour=colour)
    return embed


async def quote_embed(id: int, text: str, authorid: int, date: datetime.date, url: str = None, colour: int = 0x2F3136) -> discord.Embed:
    embed = discord.Embed(colour = colour, title=f'Quote #{id}', description=f'''
    **❝{text}❞**
    By <@{authorid}> on {datetime.datetime.strptime(str(date), '%Y-%m-%d').strftime('%d-%m-%Y')}
    ''')
    if url != None:
        embed.set_image(url=url)
    try:
        avatar_url = (await bot.fetch_user(authorid)).avatar.url
    except discord.NotFound:
        avatar_url = f'https://cdn.discordapp.com/embed/avatars/{authorid % 5}.png'
    embed.set_thumbnail(url=avatar_url)
    return embed


async def response_embed(title: str, text: str, colour: int = 0x2F3136) -> discord.Embed:
    embed = discord.Embed(colour=colour, title=title, description=text)
    return embed


async def get_quote_data(id: int, guild_id: int) -> list:
    async with bot.pool.acquire() as con:
        quote_data = await con.fetch(f'''
        SELECT * FROM (
            SELECT ROW_NUMBER() OVER() AS id,
            true_id, text, authorid, date, url
            FROM quotes_{guild_id}
            ORDER BY true_id ASC
        ) AS _
        WHERE id = $1;
        ''', id)
    return list(quote_data[0])


async def get_count(guild_id: int, text: str = None, has_image: bool = None, authorid: int = None) -> int:
    bool_to_null = {True: 'NOT NULL', False: 'NULL'}
    args = [text, authorid]
    args = [x for x in args if x is not None]
    request = f'SELECT COUNT(*) FROM quotes_{guild_id}'
    counter = 1
    constraints_added = False
    if args:
        request += '\nWHERE '
    
    if text is not None:
        constraints_added = True
        request += f'text LIKE ${counter}'
        counter += 1
    
    if has_image is not None:
        if constraints_added:
            request += '\nAND '
        constraints_added = True
        request += f'url IS {"NULL" if not bool_to_null[has_image] else "NOT NULL"}'

    if authorid is not None:
        if constraints_added:
            request += '\nAND '
        constraints_added = True
        request += f'authorid = ${counter}'
        counter += 1

    async with bot.pool.acquire() as con:
        quote_count = await con.fetch(request, *args)
    return quote_count[0]['count']


async def get_page_quotes(guild_id: int, page: int, text: str = None, has_image: bool = None, authorid: int = None) -> list:
    bool_to_null = {True: 'NOT NULL', False: 'NULL'}
    offset = (page-1)*10
    args = [text, authorid]
    args = [x for x in args if x is not None]

    request = f'''SELECT * FROM (
                SELECT ROW_NUMBER() OVER() AS id,
                true_id, text, authorid, date, url
                FROM quotes_{guild_id}
                ORDER BY true_id ASC
            ) AS _'''
    counter = 1
    constraints_added = False

    if args:
        request += '\nWHERE '
    
    if text is not None:
        constraints_added = True
        request += f'text LIKE ${counter}'
        counter += 1
    
    if has_image is not None:
        if constraints_added:
            request += '\nAND '
        constraints_added = True
        request += f'url IS {bool_to_null[has_image]}'

    if authorid is not None:
        if constraints_added:
            request += '\nAND '
        constraints_added = True
        request += f'authorid = ${counter}'
        counter += 1
    
    request += f'\nLIMIT 10 OFFSET ${counter};'

    async with bot.pool.acquire() as con:
        page_quotes = await con.fetch(request, *args, offset)
    return page_quotes


async def is_admin(user_perms: discord.Permissions) -> bool:
    return (
        user_perms.administrator
        or user_perms.manage_guild
        or user_perms.manage_roles
        or user_perms.manage_messages
        or user_perms.manage_channels
    )


async def is_mod(user_perms: discord.Permissions) -> bool:
    return (
        await is_admin(user_perms)
        or user_perms.moderate_members
        or user_perms.ban_members
        or user_perms.kick_members
        )


class Confirm(discord.ui.View): 
    def __init__(self):
        super().__init__()
        self.cancelled = None
        self.timeout = TIMEOUT
    
    @discord.ui.button(label='Cancel', style=discord.ButtonStyle.gray)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cancelled = True
        self.stop()
    
    @discord.ui.button(label='Confirm', style=discord.ButtonStyle.red)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cancelled = False
        self.stop()


class PageScroll(discord.ui.View):
    def __init__(self, _page: int, _total: int, _text: str = None, _has_image: bool = None, _authorid: int = None):
        super().__init__()
        self.page = _page
        self.total = _total
        self.text = _text
        self.has_image = _has_image
        self.authorid = _authorid
        self.timeout = TIMEOUT

        if self.page == 1:
            self.first.disabled = True
            self.previous.disabled = True
        if self.page == self.total:
            self.last.disabled = True
            self.next.disabled = True
        self.count.label = f'{self.page}/{self.total}'

    @discord.ui.button(label='First', style=discord.ButtonStyle.green)
    async def first(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = 1
        self.previous.disabled = True
        button.disabled = True
        self.count.label = f'{self.page}/{self.total}'
        if self.next.disabled or self.last.disabled:
            self.next.disabled = False
            self.last.disabled = False
        
        page_quotes = await get_page_quotes(interaction.guild_id, self.page, self.text, self.has_image, self.authorid)
        embed = await make_quote_list(page_quotes, self.page, self.total)
        await interaction.response.edit_message(view=self, embed=embed)

    @discord.ui.button(label='Previous', style=discord.ButtonStyle.green)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page == 2:
            button.disabled = True
            self.first.disabled = True
        self.page -= 1
        self.count.label = f'{self.page}/{self.total}'
        if self.next.disabled or self.last.disabled:
            self.next.disabled = False
            self.last.disabled = False
        
        page_quotes = page_quotes = await get_page_quotes(interaction.guild_id, self.page, self.text, self.has_image, self.authorid)
        embed = await make_quote_list(page_quotes, self.page, self.total)
        await interaction.response.edit_message(view=self, embed=embed)

    @discord.ui.button(label='N/A', style=discord.ButtonStyle.gray, disabled=True)
    async def count(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(label='Next', style=discord.ButtonStyle.green)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page+1 == self.total:
            button.disabled = True
            self.last.disabled = True
        self.page += 1
        self.count.label = f'{self.page}/{self.total}'
        if self.previous.disabled or self.first.disabled:
            self.previous.disabled = False
            self.first.disabled = False
        
        page_quotes = await get_page_quotes(interaction.guild_id, self.page, self.text, self.has_image, self.authorid)
        embed = await make_quote_list(page_quotes, self.page, self.total)
        await interaction.response.edit_message(view=self, embed=embed)

    @discord.ui.button(label='Last', style=discord.ButtonStyle.green)
    async def last(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = self.total
        button.disabled = True
        self.next.disabled = True
        self.count.label = f'{self.page}/{self.total}'
        if self.previous.disabled or self.first.disabled:
            self.previous.disabled = False
            self.first.disabled = False

        page_quotes = await get_page_quotes(interaction.guild_id, self.page, self.text, self.has_image, self.authorid)
        embed = await make_quote_list(page_quotes, self.page, self.total)
        await interaction.response.edit_message(view=self, embed=embed)
    
    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        await self.message.edit(view=self)


class RepeatRandom(discord.ui.View):
    def __init__(self, _quote_count):
        super().__init__()
        self.counter = 1
        self.quote_count = _quote_count
        self.timeout = TIMEOUT
    
    @discord.ui.button(label='Random', style=discord.ButtonStyle.blurple)
    async def repeat_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.counter += 1
        id, true_id, text, authorid, date, url = await get_quote_data(random.randint(1, self.quote_count), interaction.guild_id)
        embed = await quote_embed(id, text, authorid, date, url)
        await interaction.response.edit_message(content=f'Random quote #{self.counter}', embed=embed, view=self)
    
    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        await self.message.edit(view=self)


class LongInput(discord.ui.Modal, title = 'Long Quote Input'):
    text = discord.ui.TextInput(
        label = 'Quote text',
        style = discord.TextStyle.long,
        placeholder = 'Type your quote here...',
        max_length=350
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message('Quote submitted!', ephemeral=True)
        self.stop()


# ░█████╗░░█████╗░███╗░░░███╗███╗░░░███╗░█████╗░███╗░░██╗██████╗░░██████╗
# ██╔══██╗██╔══██╗████╗░████║████╗░████║██╔══██╗████╗░██║██╔══██╗██╔════╝
# ██║░░╚═╝██║░░██║██╔████╔██║██╔████╔██║███████║██╔██╗██║██║░░██║╚█████╗░
# ██║░░██╗██║░░██║██║╚██╔╝██║██║╚██╔╝██║██╔══██║██║╚████║██║░░██║░╚═══██╗
# ╚█████╔╝╚█████╔╝██║░╚═╝░██║██║░╚═╝░██║██║░░██║██║░╚███║██████╔╝██████╔╝
# ░╚════╝░░╚════╝░╚═╝░░░░░╚═╝╚═╝░░░░░╚═╝╚═╝░░╚═╝╚═╝░░╚══╝╚═════╝░╚═════╝░


# ================ USER COMMANDS ================

save_group = Group(name='save', description='Commands to save quotes')

@save_group.command(name='text', description='Saves a single-line quote to the server\'s Quote Book.')
async def save_text(interaction: discord.Interaction, text: str):
    '''Saves a single-line quote to the server's Quote Book'''
    try:
        async with bot.pool.acquire() as con:
            current_quotes = await con.fetch(f'''
            SELECT text FROM quotes_{interaction.guild_id};
            ''')
            current_quotes = [record[0] for record in current_quotes]
            if text.lower() in current_quotes:
                embed = await response_embed('Error: Quote already exists', 'This quote has already been added!', RED)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            await con.execute(f'''
            INSERT INTO quotes_{interaction.guild_id}
            (text, authorid, date, url)
            VALUES ($1, $2, $3, $4);
            ''', text, interaction.user.id, datetime.date.today(), None)
        quote_count = await get_count(guild_id=interaction.guild_id)
        embed = await quote_embed(quote_count, text, interaction.user.id, str(datetime.date.today()), None, colour = GREEN)
        await interaction.response.send_message(f'Quote #{quote_count} added!', embed=embed)
    except Exception as ex:
        print('Exception occured in save_text:', type(ex).__name__, ex)


@save_group.command(name='image', description='Saves an image quote to the server\'s Quote Book.')
async def save_image(interaction: discord.Interaction, image: discord.Attachment, text: str = ''):
    '''Saves an image quote to the server's Quote Book'''
    try:
        if image.content_type.split('/')[0] != 'image':
            embed = await response_embed('Error: Incorrect filetype', 'File must be an image!', RED)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        async with bot.pool.acquire() as con:
            current_quotes = await con.fetch(f'''
            SELECT text, url FROM quotes_{interaction.guild_id};
            ''')
            current_text = [record[0] for record in current_quotes]
            current_urls = [record[1] for record in current_quotes]
            if text.lower() in current_text or image.url in current_urls:
                embed = await response_embed('Error: Quote already exists', 'This quote has already been added!', RED)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            await con.execute(f'''
            INSERT INTO quotes_{interaction.guild_id}
            (text, authorid, date, url)
            VALUES ($1, $2, $3, $4);
            ''', text, interaction.user.id, datetime.date.today(), image.url)
        quote_count = await get_count(guild_id=interaction.guild_id)
        embed = await quote_embed(quote_count, text, interaction.user.id, str(datetime.date.today()), image.url, colour = GREEN)
        await interaction.response.send_message(f'Quote #{quote_count} added!', embed=embed)
    except Exception as ex:
        print('Exception occured in save_image:', type(ex).__name__, ex)


@save_group.command(name='long', description='Saves a multi-line quote to the server\'s Quote Book.')
async def save_long(interaction: discord.Interaction, image: discord.Attachment = None):
    '''Saves a multi-line quote to the server's Quote Book.'''
    try:
        if image is not None and image.content_type.split('/')[0] != 'image':
            embed = await response_embed('Error: Incorrect filetype', 'File must be an image!', RED)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        modal = LongInput()
        await interaction.response.send_modal(modal)
        await modal.wait()
        text = str(modal.text)
        async with bot.pool.acquire() as con:
            current_quotes = await con.fetch(f'''
            SELECT text FROM quotes_{interaction.guild_id};
            ''')
            current_quotes = [record[0] for record in current_quotes]
            if text.lower() in current_quotes:
                await interaction.followup.send('This quote has already been added!')
                return

            await con.execute(f'''
            INSERT INTO quotes_{interaction.guild_id}
            (text, authorid, date, url)
            VALUES ($1, $2, $3, $4);
            ''', text, interaction.user.id, datetime.date.today(), None if image is None else image.url)
        quote_count = await get_count(guild_id=interaction.guild_id)
        embed = await quote_embed(quote_count, text, interaction.user.id, str(datetime.date.today()), None, colour = GREEN)
        await interaction.followup.send(f'Quote #{quote_count} added!', embed=embed)
    except Exception as ex:
        print('Exception occured in delete:', type(ex).__name__, ex)


bot.tree.add_command(save_group)


@bot.tree.command(name = 'list', description='Lists quotes from the Quote Book, 10 per page.')
async def list_quotes(interaction: discord.Interaction, page: int = 1):
    '''Lists quotes from the Quote Book, 10 per page.'''
    try:
        quote_count = await get_count(interaction.guild_id)
        if quote_count == 0:
            embed = await response_embed('Error: No quotes', f'No quotes have been added to the Quote Book yet! Add some with /save.', RED)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        page_count = quote_count//10 if quote_count%10 == 0 else quote_count//10 + 1
        if page not in range(1, page_count+1):
            embed = await response_embed('Error: Page not found', f'Page does not exist! Total pages: {page_count}', RED)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        page_quotes = await get_page_quotes(interaction.guild_id, page)
        embed = await make_quote_list(page_quotes, page, page_count)
        view = PageScroll(page, page_count)
        await interaction.response.send_message(embed=embed, view=view)
        view.message = await interaction.original_response()
    except Exception as ex:
        print('Exception occured in list_quotes:', type(ex).__name__, ex)


@bot.tree.command(name='random', description='Picks a random quote.')
async def random_quote(interaction: discord.Interaction):
    '''Picks a random quote'''
    try:
        quote_count = await get_count(guild_id=interaction.guild_id)
        if quote_count == 0:
            embed = await response_embed('Error: No quotes', f'No quotes have been added to the Quote Book yet! Add some with /save.', RED)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        id, true_id, text, authorid, date, url = await get_quote_data(random.randint(1, quote_count), interaction.guild_id)
        embed = await quote_embed(id, text, authorid, date, url)
        view = RepeatRandom(quote_count)
        await interaction.response.send_message(content='Random quote #1', embed=embed, view=view)
        view.message = await interaction.original_response()
    except Exception as ex:
        print('Exception occured in random_quote:', type(ex).__name__, ex)


@bot.tree.command(description='Shows a specific quote by id.')
async def quote(interaction: discord.Interaction, id: int):
    '''Shows a specific quote by id'''
    try:
        quote_count = await get_count(guild_id=interaction.guild_id)
        if quote_count == 0:
            embed = await response_embed('Error: No quotes', f'No quotes have been added to the Quote Book yet! Add some with /save.', RED)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        if id not in range(1, quote_count+1):
            embed = await response_embed('Error: Quote not found', f'Quote does not exist! Total quotes: {quote_count}', RED)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        id, true_id, text, authorid, date, url = await get_quote_data(id, interaction.guild_id)
        embed = await quote_embed(id, text, authorid, date, url)
        await interaction.response.send_message(embed=embed)
    except Exception as ex:
        print('Exception occured in quote:', type(ex).__name__, ex)


@bot.tree.command(description='Deletes a quote by id.')
async def delete(interaction: discord.Interaction, id: int):
    '''Deletes a specific quote by id'''
    try:
        quote_count = await get_count(guild_id=interaction.guild_id)
        if quote_count == 0:
            embed = await response_embed('Error: No quotes', f'''No quotes have been added to the Quote Book yet! Add some with /save.
            Why are you deleting quotes... when there are none?''', RED)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        if id not in range(1, quote_count+1):
            embed = await response_embed('Error: Quote not found', f'Quote does not exist! Total quotes: {quote_count}', RED)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        id, true_id, text, authorid, date, url = await get_quote_data(id, interaction.guild_id)

        if interaction.user.id != authorid and not (await is_mod(interaction.channel.permissions_for(interaction.user))):
            embed = await response_embed('Error: Not quote author', f'You are not the author of this quote!', RED)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        async with bot.pool.acquire() as con:
            await con.execute(f'''
            DELETE FROM quotes_{interaction.guild_id}
            WHERE true_id = $1;
            ''', true_id)
        embed = await quote_embed(id, text, authorid, date, url, colour=RED)
        await interaction.response.send_message(f'Quote #{id} deleted!', embed=embed)
    except Exception as ex:
        print('Exception occured in delete:', type(ex).__name__, ex)


@bot.tree.command(description='Searches for quotes satisfying specified constraints.')
async def search(interaction: discord.Interaction, contains: str = '', has_image: bool = None, author: discord.Member = None, page: int = 1):
    '''Searches for quotes containing specified text'''
    try:
        text = f'%{contains}%'
        authorid = None if author is None else author.id

        quote_count = await get_count(interaction.guild_id, text, has_image, authorid)
        page_count = quote_count//10 if quote_count%10 == 0 else quote_count//10 + 1
        if quote_count == 0:
            embed = await response_embed('Error: Quotes not found', f'No quotes matching constraints found! Maybe you made a typo?', RED)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        if page not in range(1, page_count+1):
            embed = await response_embed('Error: Page not found', f'Page does not exist! Total pages: {page_count}', RED)
            await interaction.response.send_message(embed=embed, ephemeral=True)

        page_quotes = await get_page_quotes(interaction.guild_id, page, text, has_image, authorid)
        embed = await make_quote_list(page_quotes, page, page_count)
        view = PageScroll(page, page_count, text, has_image, authorid)
        await interaction.response.send_message(content=f'Quotes found: {quote_count}', embed=embed, view=view)
        view.message = await interaction.original_response()
    except Exception as ex:
        print('Exception occured in search:', type(ex).__name__, ex)


@bot.tree.command(description='Returns the bot\'s ping.')
async def ping(interaction: discord.Interaction):
    embed = await response_embed('Pong!', f'Latency: {round(bot.latency * 1000)}ms', GREEN)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.hybrid_command()
async def help(ctx):
    '''Shows the help list.'''
    cmd_lst = [f'</{name}:{id}>\n{desc}' for name, (id, desc) in cmd_info.items()]
    embed = discord.Embed(title='QuoteBot Commands', description='\n'.join(cmd_lst))
    await ctx.send(embed=embed)


# ================ MODERATION COMMANDS ================

@bot.tree.command(description='_Admin only:_ Deletes quotes en-masse according to constraints.')
async def massdelete(interaction: discord.Interaction, contains: str = '', has_image: bool = None, author: discord.Member = None):
    '''Admin only: Deletes quotes en-masse according to constraints.'''
    try:
        if not (await is_admin(interaction.channel.permissions_for(interaction.user))):
            embed = await response_embed('Error: Missing permissions', f'''
User lacks permissions to execute the command!
Permission required (at least one of the following):
Administrator
Manage Server
Manage Roles
Manage Messages
Manage Channels
            ''', RED)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        text = f'%{contains}%'
        authorid = None if author is None else author.id

        quote_count = await get_count(interaction.guild_id, text, has_image, authorid)
        if quote_count == 0:
            embed = await response_embed('Error: Quotes not found', f'No quotes matching constraints found! Maybe you made a typo?', RED)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        view = Confirm()
        embed = await response_embed(f'WARNING: MASS DELETION: {quote_count} QUOTES', f'''
**WARNING: {quote_count} QUOTES ARE ABOUT TO BE DELETED!**
Please make sure that you have entered the correct parameters.
If you are unsure, check with </search:{cmd_info['search'][0]}> - _parameters are identical._
If you are 100% sure you want to do this, click Confirm.

__**THIS CANNOT BE UNDONE!**__
''', RED)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        await view.wait()
        if view.cancelled is None:
            embed = await response_embed('Error: Timed out', 'Confirmation timed out, so the command was cancelled.', RED)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        elif view.cancelled:
            embed = await response_embed('Cancelled', 'Command was cancelled.', GRAY)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        else: # Deletion code here:
            bool_to_null = {True: 'NOT NULL', False: 'NULL'}
            args = [text, authorid]
            args = [x for x in args if x is not None]

            request = f'''DELETE FROM quotes_{interaction.guild_id}'''
            counter = 1
            constraints_added = False

            if args:
                request += '\nWHERE '
            
            if text is not None:
                constraints_added = True
                request += f'text LIKE ${counter}'
                counter += 1
            
            if has_image is not None:
                if constraints_added:
                    request += '\nAND '
                constraints_added = True
                request += f'url IS {bool_to_null[has_image]}'

            if authorid is not None:
                if constraints_added:
                    request += '\nAND '
                constraints_added = True
                request += f'authorid = ${counter}'
                counter += 1

            async with bot.pool.acquire() as con:
                await con.execute(request, *args)
            embed = await response_embed('Quotes deleted', f'{quote_count} quotes were deleted. New quote count: {await get_count(interaction.guild_id)}', GRAY)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

    except Exception as ex:
        print('Exception occured in mass delete:', type(ex).__name__, ex)


# ░█████╗░██████╗░███╗░░░███╗██╗███╗░░██╗
# ██╔══██╗██╔══██╗████╗░████║██║████╗░██║
# ███████║██║░░██║██╔████╔██║██║██╔██╗██║
# ██╔══██║██║░░██║██║╚██╔╝██║██║██║╚████║
# ██║░░██║██████╔╝██║░╚═╝░██║██║██║░╚███║
# ╚═╝░░╚═╝╚═════╝░╚═╝░░░░░╚═╝╚═╝╚═╝░░╚══╝

# The following command is made for the explicit purpose of transferring quotes from the
# quotes channel in my private friend server (as that is where all quotes have been saved up)
# until now. I may allow this command for future access.
@bot.command()
@commands.is_owner()
async def mass_save(ctx, channel: discord.TextChannel):
    try:
        embed = await response_embed('Mass Save: Stage 1', f'**Stage 1: Command received**, started reading contents of {channel.mention}. This could take a while.')
        message = await ctx.send(embed=embed)
        all_msgs = [msg async for msg in channel.history(limit=None)][::-1]

        embed.title = 'Mass Save: Stage 2'
        embed.description += f'{NEWLINE}**Stage 2: {len(all_msgs)}** messages read, filtering through messages. This should be relatively quick.'
        await message.edit(embed=embed)
        quotes = []
        for msg in all_msgs:
            text = msg.content
            if (text.count("'") >= 2) or (text.count('"') >= 2) or (("“" in text) or ("‘" in text and "’" in text)):
                if 'drop table quotes' in text.lower():
                    continue
                msg.content = msg.content.replace('\'', '')
                quotes.append(msg)
            elif msg.attachments and msg.attachments[0].content_type.split('/')[0] == 'image':
                quotes.append(msg)

        embed.title = 'Mass Save: Stage 3'
        embed.description += f'{NEWLINE}**Stage 3: {len(quotes)}** messages filtered, saving to Quote Book. This could take a while.'
        await message.edit(embed=embed)
        await clear_table(ctx.guild.id)
        for quote in quotes:
            quote_date = str(quote.created_at).split(' ')[0].split('-')
            quote_date = datetime.date(int(quote_date[0]), int(quote_date[1]), int(quote_date[2]))
            async with bot.pool.acquire() as con:
                await con.execute(f'''
                INSERT INTO quotes_{ctx.guild.id}
                (text, authorid, date, url)
                VALUES ($1, $2, $3, $4)
                ''', quote.content, quote.author.id, quote_date, None if len(quote.attachments) == 0 else quote.attachments[0].url)

        quote_count = await get_count(guild_id=ctx.guild.id)
        embed.title = 'Mass Save: Complete'
        embed.description += f'''{NEWLINE}**Complete: {quote_count}** quotes added to the Quote Book; use {f'</list:{cmd_info["list"][0]}>'} to list them all!'''
        await message.edit(embed=embed)
    except Exception as ex:
        print('Exception occured in mass_save:', type(ex).__name__, ex)


### NOTE: Code for sync command taken from https://gist.github.com/AbstractUmbra/a9c188797ae194e592efe05fa129c57f
### Original code remains unchanged and all rights for the command go to AbstractUmbra. If needed, I will remove the command.
### (Gists don't have a license :/)
@bot.command()
@commands.guild_only()
@commands.is_owner()
async def sync(
  ctx: Context, guilds: Greedy[discord.Object], spec: Optional[Literal["~", "*", "^"]] = None) -> None:
    if not guilds:
        if spec == "~":
            synced = await ctx.bot.tree.sync(guild=ctx.guild)
        elif spec == "*":
            ctx.bot.tree.copy_global_to(guild=ctx.guild)
            synced = await ctx.bot.tree.sync(guild=ctx.guild)
        elif spec == "^":
            ctx.bot.tree.clear_commands(guild=ctx.guild)
            await ctx.bot.tree.sync(guild=ctx.guild)
            synced = []
        else:
            synced = await ctx.bot.tree.sync()

        await ctx.send(
            f"Synced {len(synced)} commands {'globally' if spec is None else 'to the current guild.'}"
        )
        return

    ret = 0
    for guild in guilds:
        try:
            await ctx.bot.tree.sync(guild=guild)
        except discord.HTTPException:
            pass
        else:
            ret += 1

    await ctx.send(f"Synced the tree to {ret}/{len(guilds)}.")

@bot.command(pass_context=True)
@commands.is_owner()
async def shutdown(ctx):
    await bot.close()

@bot.event
async def on_ready():
    print(f'We have logged in as {bot.user}')

if __name__ == '__main__':
    asyncio.run(main())
