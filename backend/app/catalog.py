import asyncio
import hashlib
import json
import logging
import os
import random
import re
import time
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

import httpx

from . import config as _config

log = logging.getLogger(__name__)

ITUNES_SEARCH = "https://itunes.apple.com/search"
ITUNES_LOOKUP = "https://itunes.apple.com/lookup"
EXTRA_TRACK_PREFIX = "itunes_"
# iTunes storefront for player-added songs (in-game search + lookup). The DE
# store is a superset for a German friend group — it carries international hits
# AND German tracks (Deutschrap/Schlager) the US store lists without a preview.
# Search, lookup, and the year heuristic must all use the SAME store: a track_id
# found in one store may have no previewUrl in another, which would fail the add.
EXTRA_SONG_STORE = "DE"
# Paths live in app.config (one BEATSTER_DATA_DIR knob + individual overrides);
# imported as module globals so tests can keep monkeypatching them here.
CACHE_PATH = _config.CATALOG_CACHE_PATH
COMMUNITY_PATH = _config.COMMUNITY_PATH
CACHE_TTL_S = 30 * 24 * 3600  # 30 days (catalog is shipped as a pre-built cache)
CACHE_VERSION = 5  # bumped for the large catalog expansion (2026-06-13)


@dataclass(frozen=True, slots=True)
class Track:
    id: str
    title: str
    artist: str
    year: int
    preview_url: str
    artwork_url: str | None = None
    category: str = "music"  # "music" | "film_tv"


# (search query, expected artist substring, curated original-release year)
# iTunes returns the release date of whatever SKU it picks (often a remaster
# or compilation) — the third tuple element is the manual override we trust.
SEED_TRACKS: list[tuple[str, str, int]] = [
    # 1960s
    ("Stand By Me Ben E King", "Ben E. King", 1961),
    ("I Want to Hold Your Hand Beatles", "Beatles", 1963),
    ("House of the Rising Sun Animals", "Animals", 1964),
    ("Yesterday Beatles", "Beatles", 1965),
    ("Satisfaction Rolling Stones", "Rolling Stones", 1965),
    ("I Got You I Feel Good James Brown", "James Brown", 1965),
    ("Marmor Stein und Eisen bricht Drafi Deutscher", "Drafi Deutscher", 1965),
    ("These Boots Are Made for Walkin Nancy Sinatra", "Nancy Sinatra", 1966),
    ("Good Vibrations Beach Boys", "Beach Boys", 1966),
    ("Light My Fire The Doors", "Doors", 1967),
    ("Hey Jude Beatles", "Beatles", 1968),
    ("Mrs Robinson Simon and Garfunkel", "Simon", 1968),
    # 1970s
    ("Let It Be Beatles", "Beatles", 1970),
    ("Imagine John Lennon", "John Lennon", 1971),
    ("Stairway to Heaven Led Zeppelin", "Led Zeppelin", 1971),
    ("Rocket Man Elton John", "Elton John", 1972),
    ("Über den Wolken Reinhard Mey", "Reinhard Mey", 1974),
    ("Bohemian Rhapsody Queen", "Queen", 1975),
    ("Mamma Mia ABBA", "ABBA", 1975),
    ("Born to Run Bruce Springsteen", "Bruce Springsteen", 1975),
    ("Walk This Way Aerosmith", "Aerosmith", 1975),
    ("Hotel California Eagles", "Eagles", 1976),
    ("Dancing Queen ABBA", "ABBA", 1976),
    ("Stayin Alive Bee Gees", "Bee Gees", 1977),
    ("We Are the Champions Queen", "Queen", 1977),
    ("YMCA Village People", "Village People", 1978),
    ("I Will Survive Gloria Gaynor", "Gloria Gaynor", 1978),
    # 1980s
    ("Don't Stop Believin Journey", "Journey", 1981),
    ("Tainted Love Soft Cell", "Soft Cell", 1981),
    ("Major Tom Peter Schilling", "Peter Schilling", 1982),
    ("Eye of the Tiger Survivor", "Survivor", 1982),
    ("Billie Jean Michael Jackson", "Michael Jackson", 1982),
    ("Africa Toto", "Toto", 1982),
    ("Every Breath You Take Police", "Police", 1983),
    ("Sweet Dreams Eurythmics", "Eurythmics", 1983),
    ("Beat It Michael Jackson", "Michael Jackson", 1983),
    ("99 Luftballons Nena", "Nena", 1983),
    ("Like a Virgin Madonna", "Madonna", 1984),
    ("Take On Me a-ha", "a-ha", 1985),
    ("Livin on a Prayer Bon Jovi", "Bon Jovi", 1986),
    ("Sweet Child O Mine Guns N Roses", "Guns N' Roses", 1987),
    ("I Wanna Dance with Somebody Whitney Houston", "Whitney Houston", 1987),
    # 1990s
    ("Wind of Change Scorpions", "Scorpions", 1990),
    ("Smells Like Teen Spirit Nirvana", "Nirvana", 1991),
    ("Black or White Michael Jackson", "Michael Jackson", 1991),
    ("Losing My Religion REM", "R.E.M.", 1991),
    ("Creep Radiohead", "Radiohead", 1992),
    ("Wonderwall Oasis", "Oasis", 1995),
    ("Macarena Los del Rio", "Los del", 1993),  # SKU is the original version
    ("Killing Me Softly Fugees", "Fugees", 1996),
    ("Wannabe Spice Girls", "Spice Girls", 1996),
    ("Tubthumping Chumbawamba", "Chumbawamba", 1997),
    ("Bitter Sweet Symphony The Verve", "Verve", 1997),
    ("Du hast Rammstein", "Rammstein", 1997),
    ("Baby One More Time Britney Spears", "Britney Spears", 1998),
    ("I Want It That Way Backstreet Boys", "Backstreet Boys", 1999),
    ("Anton aus Tirol DJ Ötzi", "Ötzi", 1999),
    # 2000s
    ("Beautiful Day U2", "U2", 2000),
    ("Sonne Rammstein", "Rammstein", 2001),
    ("Lose Yourself Eminem", "Eminem", 2002),
    ("Hey Ya OutKast", "OutKast", 2003),
    ("In Da Club 50 Cent", "50 Cent", 2003),
    ("Crazy in Love Beyonce", "Beyoncé", 2003),
    ("Toxic Britney Spears", "Britney Spears", 2003),
    ("Seven Nation Army White Stripes", "White Stripes", 2003),
    ("Mr Brightside The Killers", "The Killers", 2004),
    ("Yeah Usher", "Usher", 2004),
    ("Bad Day Daniel Powter", "Daniel Powter", 2005),
    ("Hey There Delilah Plain White Ts", "Plain White", 2006),
    ("Apologize OneRepublic", "OneRepublic", 2007),
    ("Umbrella Rihanna", "Rihanna", 2007),
    ("Single Ladies Beyonce", "Beyoncé", 2008),
    # 2010s
    ("Rolling in the Deep Adele", "Adele", 2010),
    ("Somebody That I Used to Know Gotye", "Gotye", 2011),
    ("Get Lucky Daft Punk", "Daft Punk", 2013),
    ("Happy Pharrell Williams", "Pharrell Williams", 2013),
    ("Royals Lorde", "Lorde", 2013),
    ("Wake Me Up Avicii", "Avicii", 2013),
    ("Counting Stars OneRepublic", "OneRepublic", 2013),
    ("Atemlos durch die Nacht Helene Fischer", "Helene Fischer", 2013),
    ("Take Me to Church Hozier", "Hozier", 2014),
    ("Auf uns Andreas Bourani", "Andreas Bourani", 2014),
    ("Uptown Funk Mark Ronson", "Mark Ronson", 2014),
    ("Shape of You Ed Sheeran", "Ed Sheeran", 2017),
    ("Despacito Luis Fonsi", "Luis Fonsi", 2017),
    ("Old Town Road Lil Nas X", "Lil Nas X", 2019),
    ("Blinding Lights The Weeknd", "The Weeknd", 2019),
    # 2020s
    ("Watermelon Sugar Harry Styles", "Harry Styles", 2020),
    ("Levitating Dua Lipa", "Dua Lipa", 2020),
    ("Heat Waves Glass Animals", "Glass Animals", 2020),
    ("Save Your Tears The Weeknd", "The Weeknd", 2020),
    ("Drivers License Olivia Rodrigo", "Olivia Rodrigo", 2021),
    ("Bad Habits Ed Sheeran", "Ed Sheeran", 2021),
    ("Stay Kid LAROI Justin Bieber", "Kid LAROI", 2021),
    ("As It Was Harry Styles", "Harry Styles", 2022),
    ("Anti-Hero Taylor Swift", "Taylor Swift", 2022),
    ("Layla DJ Robin Schürze", "DJ Robin", 2022),
    ("Flowers Miley Cyrus", "Miley Cyrus", 2023),
    # ============================================================
    # Expansion 2026-06-13 — international classics, German hits /
    # Schlager / NDW, Deutschrap, and recent/viral hits. Years are
    # the curated original-release year (source of truth).
    # ============================================================
    # ---- 1950s ----
    ("Rock Around the Clock Bill Haley", "Bill Haley", 1955),
    ("Tutti Frutti Little Richard", "Little Richard", 1955),
    ("Jailhouse Rock Elvis Presley", "Elvis Presley", 1957),
    ("Great Balls of Fire Jerry Lee Lewis", "Jerry Lee Lewis", 1957),
    ("Johnny B. Goode Chuck Berry", "Chuck Berry", 1958),
    ("La Bamba Ritchie Valens", "Ritchie Valens", 1958),
    ("What'd I Say Ray Charles", "Ray Charles", 1959),
    # ---- 1960s ----
    ("Twist and Shout The Beatles", "Beatles", 1963),
    ("My Girl The Temptations", "Temptations", 1964),
    ("Oh Pretty Woman Roy Orbison", "Roy Orbison", 1964),
    ("Paint It Black The Rolling Stones", "Rolling Stones", 1966),
    ("Wild Thing The Troggs", "Troggs", 1966),
    ("Respect Aretha Franklin", "Aretha Franklin", 1967),
    ("A Whiter Shade of Pale Procol Harum", "Procol Harum", 1967),
    ("Brown Eyed Girl Van Morrison", "Van Morrison", 1967),
    ("Sunshine of Your Love Cream", "Cream", 1967),
    ("Born to Be Wild Steppenwolf", "Steppenwolf", 1968),
    ("Sympathy for the Devil The Rolling Stones", "Rolling Stones", 1968),
    ("Sugar Sugar The Archies", "Archies", 1969),
    ("Bad Moon Rising Creedence Clearwater Revival", "Creedence", 1969),
    ("Sweet Caroline Neil Diamond", "Neil Diamond", 1969),
    # ---- 1970s ----
    ("Layla Derek and the Dominos", "Derek", 1970),
    ("Lola The Kinks", "Kinks", 1970),
    ("Your Song Elton John", "Elton John", 1970),
    ("American Pie Don McLean", "Don McLean", 1971),
    ("Maggie May Rod Stewart", "Rod Stewart", 1971),
    ("Life on Mars David Bowie", "David Bowie", 1971),
    ("Take Me Home Country Roads John Denver", "John Denver", 1971),
    ("Heart of Gold Neil Young", "Neil Young", 1972),
    ("Superstition Stevie Wonder", "Stevie Wonder", 1972),
    ("Lean on Me Bill Withers", "Bill Withers", 1972),
    ("Money Pink Floyd", "Pink Floyd", 1973),
    ("Dream On Aerosmith", "Aerosmith", 1973),
    ("Killer Queen Queen", "Queen", 1974),
    ("Waterloo ABBA", "ABBA", 1974),
    ("Sweet Home Alabama Lynyrd Skynyrd", "Lynyrd Skynyrd", 1974),
    ("No Woman No Cry Bob Marley", "Bob Marley", 1974),
    ("Griechischer Wein Udo Jürgens", "Udo Jürgens", 1974),
    ("Wish You Were Here Pink Floyd", "Pink Floyd", 1975),
    ("Fernando ABBA", "ABBA", 1976),
    ("More Than a Feeling Boston", "Boston", 1976),
    ("Daddy Cool Boney M.", "Boney M", 1976),
    ("Heroes David Bowie", "David Bowie", 1977),
    ("Go Your Own Way Fleetwood Mac", "Fleetwood Mac", 1977),
    ("Dreams Fleetwood Mac", "Fleetwood Mac", 1977),
    ("God Save the Queen Sex Pistols", "Sex Pistols", 1977),
    ("Rivers of Babylon Boney M.", "Boney M", 1978),
    ("Rasputin Boney M.", "Boney M", 1978),
    ("September Earth Wind and Fire", "Earth", 1978),
    ("Le Freak Chic", "Chic", 1978),
    ("Don't Stop Me Now Queen", "Queen", 1978),
    ("Sultans of Swing Dire Straits", "Dire Straits", 1978),
    ("Heart of Glass Blondie", "Blondie", 1978),
    ("Highway to Hell AC/DC", "AC/DC", 1979),
    ("Another Brick in the Wall Pink Floyd", "Pink Floyd", 1979),
    ("My Sharona The Knack", "Knack", 1979),
    ("I Was Made for Lovin You Kiss", "Kiss", 1979),
    # ---- 1980s ----
    ("Could You Be Loved Bob Marley", "Bob Marley", 1980),
    ("In the Air Tonight Phil Collins", "Phil Collins", 1981),
    ("Der Kommissar Falco", "Falco", 1981),
    ("Tom Sawyer Rush", "Rush", 1981),
    ("Skandal im Sperrbezirk Spider Murphy Gang", "Spider Murphy Gang", 1981),
    ("Da Da Da Trio", "Trio", 1982),
    ("Ein bisschen Frieden Nicole", "Nicole", 1982),
    ("Total Eclipse of the Heart Bonnie Tyler", "Bonnie Tyler", 1983),
    ("Girls Just Want to Have Fun Cyndi Lauper", "Cyndi Lauper", 1983),
    ("You're My Heart You're My Soul Modern Talking", "Modern Talking", 1984),
    ("Forever Young Alphaville", "Alphaville", 1984),
    ("Big in Japan Alphaville", "Alphaville", 1984),
    ("Männer Herbert Grönemeyer", "Grönemeyer", 1984),
    ("Time After Time Cyndi Lauper", "Cyndi Lauper", 1984),
    ("Jump Van Halen", "Van Halen", 1984),
    ("When Doves Cry Prince", "Prince", 1984),
    ("Purple Rain Prince", "Prince", 1984),
    ("Wake Me Up Before You Go-Go Wham!", "Wham", 1984),
    ("Careless Whisper George Michael", "George Michael", 1984),
    ("Footloose Kenny Loggins", "Kenny Loggins", 1984),
    ("Dancing in the Dark Bruce Springsteen", "Bruce Springsteen", 1984),
    ("Material Girl Madonna", "Madonna", 1985),
    ("Money for Nothing Dire Straits", "Dire Straits", 1985),
    ("Everybody Wants to Rule the World Tears for Fears", "Tears for Fears", 1985),
    ("Don't You Forget About Me Simple Minds", "Simple Minds", 1985),
    ("The Power of Love Huey Lewis and the News", "Huey Lewis", 1985),
    ("Rock Me Amadeus Falco", "Falco", 1985),
    ("Cheri Cheri Lady Modern Talking", "Modern Talking", 1985),
    ("Running Up That Hill Kate Bush", "Kate Bush", 1985),
    ("The Final Countdown Europe", "Europe", 1986),
    ("Walk Like an Egyptian The Bangles", "Bangles", 1986),
    ("West End Girls Pet Shop Boys", "Pet Shop Boys", 1986),
    ("Never Gonna Give You Up Rick Astley", "Rick Astley", 1987),
    ("With or Without You U2", "U2", 1987),
    ("Faith George Michael", "George Michael", 1987),
    ("Pour Some Sugar on Me Def Leppard", "Def Leppard", 1987),
    ("Need You Tonight INXS", "INXS", 1987),
    ("Don't Worry Be Happy Bobby McFerrin", "Bobby McFerrin", 1988),
    ("Westerland Die Ärzte", "Die Ärzte", 1988),
    ("Hier kommt Alex Die Toten Hosen", "Toten Hosen", 1988),
    ("Like a Prayer Madonna", "Madonna", 1989),
    ("Another Day in Paradise Phil Collins", "Phil Collins", 1989),
    ("Pump Up the Jam Technotronic", "Technotronic", 1989),
    ("Looking for Freedom David Hasselhoff", "Hasselhoff", 1989),
    # ---- 1990s ----
    ("Nothing Compares 2 U Sinéad O'Connor", "Sinéad", 1990),
    ("Verdammt ich lieb dich Matthias Reim", "Matthias Reim", 1990),
    ("Enter Sandman Metallica", "Metallica", 1991),
    ("Nothing Else Matters Metallica", "Metallica", 1991),
    ("Under the Bridge Red Hot Chili Peppers", "Red Hot Chili Peppers", 1991),
    ("November Rain Guns N Roses", "Guns N' Roses", 1991),
    ("Jeremy Pearl Jam", "Pearl Jam", 1991),
    ("I Will Always Love You Whitney Houston", "Whitney Houston", 1992),
    ("Tears in Heaven Eric Clapton", "Eric Clapton", 1992),
    ("End of the Road Boyz II Men", "Boyz II Men", 1992),
    ("Rhythm Is a Dancer Snap!", "Snap", 1992),
    ("Die da Die Fantastischen Vier", "Fantastischen Vier", 1992),
    ("What Is Love Haddaway", "Haddaway", 1993),
    ("Mr. Vain Culture Beat", "Culture Beat", 1993),
    ("The Sign Ace of Base", "Ace of Base", 1993),
    ("Linger The Cranberries", "Cranberries", 1993),
    ("Schrei nach Liebe Die Ärzte", "Die Ärzte", 1993),
    ("Zombie The Cranberries", "Cranberries", 1994),
    ("Cotton Eye Joe Rednex", "Rednex", 1994),
    ("Waterfalls TLC", "TLC", 1994),
    ("Gangsta's Paradise Coolio", "Coolio", 1995),
    ("California Love 2Pac", "2Pac", 1995),
    ("Lemon Tree Fool's Garden", "Fool's Garden", 1995),
    ("Children Robert Miles", "Robert Miles", 1995),
    ("Don't Look Back in Anger Oasis", "Oasis", 1995),
    ("Coco Jamboo Mr. President", "Mr. President", 1996),
    ("Freed from Desire Gala", "Gala", 1996),
    ("No Diggity Blackstreet", "Blackstreet", 1996),
    ("Barbie Girl Aqua", "Aqua", 1997),
    ("MMMBop Hanson", "Hanson", 1997),
    ("Torn Natalie Imbruglia", "Natalie Imbruglia", 1997),
    ("Truly Madly Deeply Savage Garden", "Savage Garden", 1997),
    ("My Heart Will Go On Celine Dion", "Céline Dion", 1997),
    ("Männer sind Schweine Die Ärzte", "Die Ärzte", 1998),
    ("Believe Cher", "Cher", 1998),
    ("Music Sounds Better with You Stardust", "Stardust", 1998),
    ("Praise You Fatboy Slim", "Fatboy Slim", 1998),
    ("MfG Die Fantastischen Vier", "Fantastischen Vier", 1999),
    ("Blue Da Ba Dee Eiffel 65", "Eiffel 65", 1999),
    ("Better Off Alone Alice Deejay", "Alice DeeJay", 1999),
    ("Californication Red Hot Chili Peppers", "Red Hot Chili Peppers", 1999),
    ("Mambo No. 5 Lou Bega", "Lou Bega", 1999),
    # ---- 2000s ----
    ("It Wasn't Me Shaggy", "Shaggy", 2000),
    ("Bye Bye Bye NSYNC", "NSYNC", 2000),
    ("In the End Linkin Park", "Linkin Park", 2000),
    ("Last Resort Papa Roach", "Papa Roach", 2000),
    ("Yellow Coldplay", "Coldplay", 2000),
    ("Survivor Destiny's Child", "Destiny's Child", 2001),
    ("Chop Suey System of a Down", "System of a Down", 2001),
    ("Drops of Jupiter Train", "Train", 2001),
    ("Dickes B Seeed", "Seeed", 2001),
    ("Ein Kompliment Sportfreunde Stiller", "Sportfreunde Stiller", 2002),
    ("Hot in Herre Nelly", "Nelly", 2002),
    ("Without Me Eminem", "Eminem", 2002),
    ("By the Way Red Hot Chili Peppers", "Red Hot Chili Peppers", 2002),
    ("Complicated Avril Lavigne", "Avril Lavigne", 2002),
    ("Cry Me a River Justin Timberlake", "Justin Timberlake", 2002),
    ("Clocks Coldplay", "Coldplay", 2002),
    ("Bring Me to Life Evanescence", "Evanescence", 2003),
    ("Numb Linkin Park", "Linkin Park", 2003),
    ("Where Is the Love Black Eyed Peas", "Black Eyed Peas", 2003),
    ("Are You Gonna Be My Girl Jet", "Jet", 2003),
    ("Guten Tag Wir sind Helden", "Wir sind Helden", 2003),
    ("Take Me Out Franz Ferdinand", "Franz Ferdinand", 2004),
    ("Symphonie Silbermond", "Silbermond", 2004),
    ("Feel Good Inc Gorillaz", "Gorillaz", 2005),
    ("Sugar We're Goin Down Fall Out Boy", "Fall Out Boy", 2005),
    ("You're Beautiful James Blunt", "James Blunt", 2005),
    ("Durch den Monsun Tokio Hotel", "Tokio Hotel", 2005),
    ("Dieser Weg Xavier Naidoo", "Xavier Naidoo", 2005),
    ("Nur ein Wort Wir sind Helden", "Wir sind Helden", 2005),
    ("Hips Don't Lie Shakira", "Shakira", 2006),
    ("Crazy Gnarls Barkley", "Gnarls Barkley", 2006),
    ("SexyBack Justin Timberlake", "Justin Timberlake", 2006),
    ("Chasing Cars Snow Patrol", "Snow Patrol", 2006),
    ("Welcome to the Black Parade My Chemical Romance", "My Chemical Romance", 2006),
    ("Stronger Kanye West", "Kanye West", 2007),
    ("Low Flo Rida", "Flo Rida", 2007),
    ("Bleeding Love Leona Lewis", "Leona Lewis", 2007),
    ("Paper Planes M.I.A.", "M.I.A.", 2007),
    ("Crank That Soulja Boy", "Soulja Boy", 2007),
    ("Spring nicht Tokio Hotel", "Tokio Hotel", 2007),
    ("Junge Die Ärzte", "Die Ärzte", 2007),
    ("Viva la Vida Coldplay", "Coldplay", 2008),
    ("Poker Face Lady Gaga", "Lady Gaga", 2008),
    ("I Kissed a Girl Katy Perry", "Katy Perry", 2008),
    ("Use Somebody Kings of Leon", "Kings of Leon", 2008),
    ("Sex on Fire Kings of Leon", "Kings of Leon", 2008),
    ("Kids MGMT", "MGMT", 2008),
    ("Electric Feel MGMT", "MGMT", 2008),
    ("Halo Beyonce", "Beyoncé", 2008),
    ("Bilder im Kopf Sido", "Sido", 2012),  # was wrongly curated as 2008
    ("So What P!nk", "P!nk", 2008),
    ("Haus am See Peter Fox", "Peter Fox", 2008),
    ("Alles neu Peter Fox", "Peter Fox", 2008),
    ("I Gotta Feeling Black Eyed Peas", "Black Eyed Peas", 2009),
    ("Empire State of Mind Jay-Z Alicia Keys", "-Z", 2009),
    ("Sweet Disposition The Temper Trap", "Temper Trap", 2009),
    ("Fireflies Owl City", "Owl City", 2009),
    ("Stadt Cassandra Steen", "Cassandra Steen", 2009),
    # ---- 2010s ----
    ("Dynamite Taio Cruz", "Taio Cruz", 2010),
    ("Love the Way You Lie Eminem", "Eminem", 2010),
    ("Just the Way You Are Bruno Mars", "Bruno Mars", 2010),
    ("Grenade Bruno Mars", "Bruno Mars", 2010),
    ("Party Rock Anthem LMFAO", "LMFAO", 2011),
    ("Moves Like Jagger Maroon 5", "Maroon 5", 2011),
    ("Pumped Up Kicks Foster the People", "Foster the People", 2011),
    ("We Found Love Rihanna", "Rihanna", 2011),
    ("Someone Like You Adele", "Adele", 2011),
    ("Set Fire to the Rain Adele", "Adele", 2011),
    ("Nur in meinem Kopf Andreas Bourani", "Andreas Bourani", 2011),
    ("Du Cro", "Cro", 2012),  # Raop; was wrongly curated as 2014
    ("Lila Wolken Marteria Yasha Miss Platnum", "Marteria", 2012),
    ("Call Me Maybe Carly Rae Jepsen", "Carly Rae Jepsen", 2012),
    ("Gangnam Style PSY", "PSY", 2012),
    ("Ho Hey The Lumineers", "Lumineers", 2012),
    ("Thrift Shop Macklemore", "Macklemore", 2012),
    ("Tage wie diese Die Toten Hosen", "Toten Hosen", 2012),
    ("Radioactive Imagine Dragons", "Imagine Dragons", 2012),
    ("Demons Imagine Dragons", "Imagine Dragons", 2012),
    ("Let Her Go Passenger", "Passenger", 2012),
    ("Can't Hold Us Macklemore", "Macklemore", 2013),
    ("Wrecking Ball Miley Cyrus", "Miley Cyrus", 2013),
    ("Roar Katy Perry", "Katy Perry", 2013),
    ("Dark Horse Katy Perry", "Katy Perry", 2013),
    ("Story of My Life One Direction", "One Direction", 2013),
    ("Sweater Weather The Neighbourhood", "Neighbourhood", 2013),
    ("Pompeii Bastille", "Bastille", 2013),
    ("Timber Pitbull Kesha", "Pitbull", 2013),
    ("All of Me John Legend", "John Legend", 2013),
    ("Riptide Vance Joy", "Vance Joy", 2013),
    ("Au Revoir Mark Forster", "Mark Forster", 2014),
    ("Stay with Me Sam Smith", "Sam Smith", 2014),
    ("Thinking Out Loud Ed Sheeran", "Ed Sheeran", 2014),
    ("Chandelier Sia", "Sia", 2014),
    ("Rather Be Clean Bandit", "Clean Bandit", 2014),
    ("Budapest George Ezra", "George Ezra", 2014),
    ("Lieblingsmensch Namika", "Namika", 2015),
    ("Hello Adele", "Adele", 2015),
    ("7 Years Lukas Graham", "Lukas Graham", 2015),
    ("Astronaut Sido Andreas Bourani", "Sido", 2015),
    ("Lush Life Zara Larsson", "Zara Larsson", 2015),
    ("Cheap Thrills Sia", "Sia", 2016),
    ("Chöre Mark Forster", "Mark Forster", 2016),
    ("80 Millionen Max Giesinger", "Max Giesinger", 2016),
    ("Can't Stop the Feeling Justin Timberlake", "Justin Timberlake", 2016),
    ("Closer The Chainsmokers", "Chainsmokers", 2016),
    ("This Is What You Came For Calvin Harris", "Calvin Harris", 2016),
    ("One Dance Drake", "Drake", 2016),
    ("Pocahontas AnnenMayKantereit", "AnnenMayKantereit", 2016),
    ("Johnny Däpp Lorenz Büffel", "Lorenz Büffel", 2016),
    ("Believer Imagine Dragons", "Imagine Dragons", 2017),
    ("Thunder Imagine Dragons", "Imagine Dragons", 2017),
    ("Havana Camila Cabello", "Camila Cabello", 2017),
    ("Perfect Ed Sheeran", "Ed Sheeran", 2017),
    ("Bausa Was du Liebe nennst", "Bausa", 2017),
    ("Sowieso Mark Forster", "Mark Forster", 2017),
    ("New Rules Dua Lipa", "Dua Lipa", 2017),
    ("rockstar Post Malone", "Post Malone", 2017),
    ("Cherry Lady Capital Bra", "Capital Bra", 2018),
    ("In My Mind Dynoro Gigi D'Agostino", "Dynoro", 2018),
    ("Je ne parle pas français Namika", "Namika", 2018),
    ("Cordula Grün Die Draufgänger", "Draufgänger", 2018),
    ("God's Plan Drake", "Drake", 2018),
    ("Shotgun George Ezra", "George Ezra", 2018),
    ("Shallow Lady Gaga Bradley Cooper", "Lady Gaga", 2018),
    ("Sunflower Post Malone Swae Lee", "Post Malone", 2018),
    ("Vincent Sarah Connor", "Sarah Connor", 2019),
    ("bad guy Billie Eilish", "Billie Eilish", 2019),
    ("Someone You Loved Lewis Capaldi", "Lewis Capaldi", 2019),
    ("Dance Monkey Tones and I", "Tones and I", 2019),
    ("Señorita Shawn Mendes Camila Cabello", "Shawn Mendes", 2019),
    ("Circles Post Malone", "Post Malone", 2019),
    ("Cruel Summer Taylor Swift", "Taylor Swift", 2019),
    ("Don't Start Now Dua Lipa", "Dua Lipa", 2019),
    # ---- 2020s ----
    ("Bläulich Apache 207", "Apache 207", 2020),
    ("Physical Dua Lipa", "Dua Lipa", 2020),
    ("Mood 24kGoldn", "24kGoldn", 2020),
    ("Dynamite BTS", "BTS", 2020),
    ("good 4 u Olivia Rodrigo", "Olivia Rodrigo", 2021),
    ("Montero Lil Nas X", "Lil Nas X", 2021),
    ("Peaches Justin Bieber", "Justin Bieber", 2021),
    ("Industry Baby Lil Nas X Jack Harlow", "Lil Nas X", 2021),
    ("Shivers Ed Sheeran", "Ed Sheeran", 2021),
    ("Beggin Måneskin", "Måneskin", 2017),
    ("2 Minuten Apache 207", "Apache 207", 2019),  # Platte EP; was 2021
    ("abcdefu Gayle", "GAYLE", 2021),
    ("About Damn Time Lizzo", "Lizzo", 2022),
    ("Unholy Sam Smith Kim Petras", "Sam Smith", 2022),
    ("I'm Good Blue David Guetta Bebe Rexha", "David Guetta", 2022),
    ("Made You Look Meghan Trainor", "Meghan Trainor", 2022),
    ("Kill Bill SZA", "SZA", 2022),
    ("Calm Down Rema Selena Gomez", "Rema", 2022),
    ("Creepin Metro Boomin The Weeknd 21 Savage", "Metro Boomin", 2022),
    ("Stick Season Noah Kahan", "Noah Kahan", 2022),
    ("Komet Udo Lindenberg Apache 207", "Apache 207", 2023),
    ("Madonna Apache 207", "Apache 207", 2021),  # single 2021; was 2023
    ("Last Night Morgan Wallen", "Morgan Wallen", 2023),
    ("Vampire Olivia Rodrigo", "Olivia Rodrigo", 2023),
    ("Paint the Town Red Doja Cat", "Doja Cat", 2023),
    ("Dance the Night Dua Lipa", "Dua Lipa", 2023),
    ("Lose Control Teddy Swims", "Teddy Swims", 2023),
    ("Houdini Dua Lipa", "Dua Lipa", 2023),
    ("Beautiful Things Benson Boone", "Benson Boone", 2024),
    ("Texas Hold Em Beyonce", "Beyoncé", 2024),
    ("Birds of a Feather Billie Eilish", "Billie Eilish", 2024),
    ("Die With a Smile Lady Gaga Bruno Mars", "Lady Gaga", 2024),
]


# Tracks whose iTunes preview only exists in the German storefront — the US
# store returns the track without a previewUrl (or only covers). Resolved with
# country="DE". Same (query, expected-artist, curated-year) shape as SEED_TRACKS.
SEED_TRACKS_DE: list[tuple[str, str, int]] = [
    ("Goldener Reiter Joachim Witt", "Joachim Witt", 1981),
    ("Das Beste Silbermond", "Silbermond", 2006),
    ("Greedy Tate McRae", "Tate McRae", 2023),
    # 2026-07-23 fixes from the tools/check_years.py report: these resolved to
    # the wrong track or a live/remix SKU in the US store; every query below
    # was verified to pick the right SKU in the DE store. Some replace
    # originals that iTunes no longer carries at all with an available hit by
    # the same artist (Roller→2002, Benzema→Benzos, Gib ihm→ON OFF,
    # Wolke 10→Meine Hand, Easy→Hi Kids; Lieben wir/Chabos/Neymar dropped).
    ("California Dreamin' The Mamas & The Papas", "Mamas", 1965),
    ("Eminem The Real Slim Shady", "Eminem", 2000),
    ("Gorillaz Clint Eastwood", "Gorillaz", 2001),
    ("American Idiot Green Day 2004", "Green Day", 2004),
    ("Sido Mein Block", "Sido", 2004),
    ("Fettes Brot An Tagen wie diesen", "Fettes Brot", 2005),
    ("Gold Digger Kanye", "Kanye West", 2005),
    ("fun. We Are Young Janelle", "fun.", 2011),
    ("fun. Some Nights", "fun.", 2012),
    ("Hi Kids Cro", "Cro", 2012),
    ("Sportfreunde Stiller Applaus Applaus", "Sportfreunde Stiller", 2013),
    ("Hulapalu Mountain Man Andreas Gabalier", "Andreas Gabalier", 2015),
    ("Hurra die Welt geht unter K.I.Z Henning May", "K.I.Z", 2015),
    ("Meine Hand Mero", "Mero", 2019),
    ("2002 Sido Apache 207", "Apache 207", 2019),
    ("ON OFF Shirin David", "Shirin David", 2019),
    ("Benzos Capital Bra", "Capital Bra", 2022),
    ("Sabrina Carpenter Espresso", "Sabrina Carpenter", 2024),
]


# Film and TV theme songs / soundtracks. Year is the work's premiere year
# (not the soundtrack release year, which iTunes may show differently).
SEED_FILM_TV_TRACKS: list[tuple[str, str, int]] = [
    # 1960s
    ("James Bond Theme Monty Norman", "Norman", 1962),
    ("Pink Panther Theme Henry Mancini", "Mancini", 1963),
    ("Doctor Who Theme Ron Grainer", "Grainer", 1963),
    ("Mission Impossible Theme Lalo Schifrin", "Schifrin", 1966),
    ("The Good the Bad and the Ugly Ennio Morricone", "Morricone", 1966),
    ("Star Trek Original Series Theme Alexander Courage", "Courage", 1966),
    # 1970s
    ("The Godfather Theme Nino Rota", "Rota", 1972),
    ("Jaws Theme John Williams", "John Williams", 1975),
    ("Rocky Gonna Fly Now Bill Conti", "Conti", 1976),
    ("Star Wars Main Theme John Williams", "John Williams", 1977),
    # 1980s
    ("Indiana Jones Raiders March John Williams", "John Williams", 1981),
    ("E.T. Flying Theme John Williams", "John Williams", 1982),
    ("Scarface Push It to the Limit Paul Engemann", "Engemann", 1983),
    ("Ghostbusters Ray Parker", "Ray Parker", 1984),
    ("Back to the Future Alan Silvestri", "Silvestri", 1985),
    ("Top Gun Danger Zone Kenny Loggins", "Kenny Loggins", 1986),
    ("Batman Theme Danny Elfman", "Elfman", 1989),
    ("Simpsons Theme Danny Elfman", "Elfman", 1989),
    ("Seinfeld Theme Jonathan Wolff", "Wolff", 1989),
    # 1990s
    ("Twin Peaks Theme Angelo Badalamenti", "Badalamenti", 1990),
    ("Fresh Prince of Bel Air Will Smith", "Will Smith", 1990),
    ("Jurassic Park Theme John Williams", "John Williams", 1993),
    ("Schindlers List Theme John Williams", "John Williams", 1993),
    ("Friends I'll Be There for You Rembrandts", "Rembrandts", 1995),
    ("South Park Theme Primus", "Primus", 1997),
    ("Family Guy Theme Walter Murphy", "Walter Murphy", 1999),
    ("Sopranos Woke Up This Morning Alabama 3", "Alabama 3", 1999),
    # 2000s
    ("Gladiator Now We Are Free Hans Zimmer", "Zimmer", 2000),
    ("Lord of the Rings Concerning Hobbits Howard Shore", "Shore", 2001),
    ("Harry Potter Hedwig Theme John Williams", "John Williams", 2001),
    ("Pirates of the Caribbean He's a Pirate Klaus Badelt", "Badelt", 2003),
    ("Lost Main Title Michael Giacchino Hollywood", "Giacchino", 2004),
    ("The Office Theme Jay Ferguson", "Ferguson", 2005),
    ("Dexter Theme Rolfe Kent", "Kent", 2006),
    ("Big Bang Theory Theme Barenaked Ladies", "Barenaked", 2007),
    ("Mad Men Theme RJD2", "RJD2", 2007),
    ("Breaking Bad Main Title Dave Porter", "Porter", 2008),
    ("The Dark Knight Theme Hans Zimmer", "Zimmer", 2008),
    # 2010s
    ("Inception Time Hans Zimmer", "Zimmer", 2010),
    ("Sherlock BBC Theme David Arnold", "Arnold", 2010),
    ("The Walking Dead Theme Bear McCreary", "McCreary", 2010),
    ("Game of Thrones Main Title Ramin Djawadi", "Djawadi", 2011),
    ("Avengers Theme Alan Silvestri", "Silvestri", 2012),
    ("Peaky Blinders Red Right Hand Nick Cave", "Nick Cave", 2013),
    ("Interstellar Cornfield Chase Hans Zimmer", "Zimmer", 2014),
    ("Westworld Theme Ramin Djawadi", "Djawadi", 2016),
    ("Stranger Things Main Theme Kyle Dixon", "Kyle Dixon", 2016),
    ("The Mandalorian Theme Ludwig Göransson", "Göransson", 2019),
    # 2020s
    ("Squid Game Way Back Then Jung Jae il", "Jung Jae", 2021),
    ("Wednesday Theme Danny Elfman", "Elfman", 2022),
]


def _slug(s: str) -> str:
    return re.sub(r"\W+", "_", s.lower()).strip("_")


# iTunes often returns the remaster SKU; the suffix is noise (and at worst a
# fake year hint) — strip it from display titles. Only remaster wording: things
# like "(Live)" carry real meaning and stay.
_REMASTER_PAREN_RE = re.compile(
    r"\s*[(\[][^)\]]*remaster[^)\]]*[)\]]", re.IGNORECASE
)
_REMASTER_DASH_RE = re.compile(
    r"\s+-\s+[^-]*\bremaster[^-]*$", re.IGNORECASE
)


def clean_title(title: str) -> str:
    cleaned = _REMASTER_PAREN_RE.sub("", title)
    cleaned = _REMASTER_DASH_RE.sub("", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned or title


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9äöüß]+", " ", s.lower()).strip()


async def _earliest_release_year(
    client: httpx.AsyncClient,
    title: str,
    artist: str,
    fallback_year: int,
) -> int:
    """Best-effort original-release year for a player-added song.

    The lookup SKU's releaseDate is often a remaster/compilation year. Search
    for the same title+artist and take the earliest plausible year across all
    matching SKUs — usually the original release.
    """
    try:
        r = await client.get(
            ITUNES_SEARCH,
            params={
                "term": f"{title} {artist}",
                "entity": "song",
                "limit": 25,
                "country": EXTRA_SONG_STORE,
            },
        )
        r.raise_for_status()
        results = r.json().get("results", [])
    except httpx.HTTPError as e:
        log.warning("earliest-year search failed for %r: %s", title, e)
        return fallback_year

    want_title = _norm(clean_title(title))
    want_artist = _norm(artist)
    max_plausible = date.today().year + 1
    years: list[int] = []
    for hit in results:
        if hit.get("kind") != "song":
            continue
        if _norm(hit.get("artistName", "")) != want_artist:
            continue
        if _norm(clean_title(hit.get("trackName", ""))) != want_title:
            continue
        try:
            year = int(hit.get("releaseDate", "")[:4])
        except ValueError:
            continue
        if 1900 <= year <= max_plausible:
            years.append(year)
    return min(years, default=fallback_year)


def _seed_hash() -> str:
    raw_music = "|".join(f"{q}::{a}::{y}::music" for q, a, y in SEED_TRACKS)
    raw_de = "|".join(f"{q}::{a}::{y}::music::DE" for q, a, y in SEED_TRACKS_DE)
    raw_film = "|".join(
        f"{q}::{a}::{y}::film_tv" for q, a, y in SEED_FILM_TV_TRACKS
    )
    return hashlib.sha256(
        f"{raw_music}#{raw_de}#{raw_film}".encode()
    ).hexdigest()[:16]


def _load_cache(strict: bool = True) -> list[Track] | None:
    """Load the on-disk catalog cache.

    strict=True  → only return it if version + seed_hash + TTL all match.
    strict=False → return whatever tracks are on disk regardless (used as a
                   fallback so a seed/version change keeps the old catalog
                   working instead of forcing a fragile live re-resolve).
    """
    try:
        with open(CACHE_PATH) as f:
            data = json.load(f)
        if strict and (
            data.get("version") != CACHE_VERSION
            or data.get("seed_hash") != _seed_hash()
            or time.time() - data.get("fetched_at", 0) > CACHE_TTL_S
        ):
            return None
        return [Track(**t) for t in data["tracks"]]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as e:
        log.warning("catalog cache invalid (%s), refetching", e)
        return None


def _save_cache(tracks: list[Track]) -> None:
    try:
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        payload = {
            "version": CACHE_VERSION,
            "seed_hash": _seed_hash(),
            "fetched_at": int(time.time()),
            "tracks": [asdict(t) for t in tracks],
        }
        with open(CACHE_PATH, "w") as f:
            json.dump(payload, f, indent=2)
    except OSError as e:
        log.warning("could not save catalog cache to %s: %s", CACHE_PATH, e)


def _load_community() -> list[Track]:
    """Load the persisted player-added (community) tracks, if any."""
    try:
        with open(COMMUNITY_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return [Track(**t) for t in data.get("tracks", [])]
    except FileNotFoundError:
        return []
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as e:
        log.warning("community tracks file invalid (%s), ignoring", e)
        return []


def remember_community_track(track: Track) -> None:
    """Persist a player-added track so it grows the catalog for future games.

    Deduped by id — re-adding the same song overwrites the old entry.
    """
    by_id = {t.id: t for t in _load_community()}
    by_id[track.id] = track
    try:
        os.makedirs(os.path.dirname(COMMUNITY_PATH) or ".", exist_ok=True)
        payload = {"tracks": [asdict(t) for t in by_id.values()]}
        with open(COMMUNITY_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
    except OSError as e:
        log.warning("could not save community track to %s: %s", COMMUNITY_PATH, e)


async def _resolve_track(
    client: httpx.AsyncClient,
    query: str,
    expect_artist: str,
    override_year: int,
    category: str = "music",
    country: str | None = None,
) -> Track | None:
    # iTunes throttles aggressive callers with 403/429; retry with backoff.
    # The catalog is large (~400 tracks), so a cold resolve is a real burst —
    # be patient (6 attempts, backoff capped at 10s) so throttled requests
    # eventually get through instead of dropping the track.
    # country: optional iTunes storefront (e.g. "DE") for tracks whose preview
    # only exists in a specific store; defaults to the US store.
    params: dict[str, str | int] = {"term": query, "entity": "song", "limit": 5}
    if country:
        params["country"] = country
    response: httpx.Response | None = None
    for attempt in range(6):
        try:
            r = await client.get(ITUNES_SEARCH, params=params)
            if r.status_code in (403, 429) and attempt < 5:
                await asyncio.sleep(min(10.0, 0.5 * (2**attempt)) + random.uniform(0, 0.4))
                continue
            r.raise_for_status()
            response = r
            break
        except httpx.HTTPError as e:
            if attempt < 5:
                await asyncio.sleep(min(10.0, 0.5 * (2**attempt)) + random.uniform(0, 0.4))
                continue
            log.warning("iTunes search failed for %r: %s", query, e)
            return None
    if response is None:
        log.warning("iTunes search failed for %r after retries", query)
        return None

    for hit in response.json().get("results", []):
        if hit.get("kind") != "song":
            continue
        if not hit.get("previewUrl"):
            continue
        if expect_artist.lower() not in hit.get("artistName", "").lower():
            continue
        itunes_year_raw = hit.get("releaseDate", "")[:4]
        if itunes_year_raw and itunes_year_raw != str(override_year):
            log.info(
                "track %r: iTunes says %s, using curated %d",
                query,
                itunes_year_raw,
                override_year,
            )
        artwork_raw = hit.get("artworkUrl100") or ""
        # iTunes artwork URLs are size-templated; bump to 600x600 for the reveal screen
        artwork_url = (
            artwork_raw.replace("100x100", "600x600") if artwork_raw else None
        )
        return Track(
            id=_slug(query),
            title=clean_title(hit["trackName"]),
            artist=hit["artistName"],
            year=override_year,
            preview_url=hit["previewUrl"],
            artwork_url=artwork_url,
            category=category,
        )

    log.warning("could not resolve track: %s", query)
    return None


class Catalog:
    def __init__(self) -> None:
        self._tracks: list[Track] = []

    def _merge_community(self) -> None:
        """Add persisted player-added tracks to the pool (overwrite by id)."""
        community = _load_community()
        if not community:
            return
        by_id = {t.id: t for t in self._tracks}
        for t in community:
            by_id[t.id] = t
        self._tracks = list(by_id.values())
        log.info("merged %d community tracks into catalog", len(community))

    async def load(self) -> None:
        cached = _load_cache()
        if cached is not None:
            self._tracks = cached
            self._merge_community()
            log.info("catalog loaded from cache: %d tracks", len(self._tracks))
            return
        # Strict cache miss (seed changed / version bump / TTL expired). The full
        # catalog is large, and resolving all of it live against iTunes at startup
        # reliably trips the rate limiter (HTTP 429) and silently drops tracks.
        # So we DON'T resolve a large catalog live here: catalog changes are
        # shipped as a pre-built cache (see tools/build_cache.py). If any previous
        # cache is on disk, keep using it until the fresh one is shipped — only a
        # true first boot with no cache at all resolves live.
        stale = _load_cache(strict=False)
        if stale is not None:
            self._tracks = stale
            self._merge_community()
            log.warning(
                "catalog seed/version changed but no matching cache on disk; "
                "using existing cache of %d tracks — ship a freshly built cache "
                "to apply the change",
                len(stale),
            )
            return
        log.info("no catalog cache found; resolving from iTunes (first boot)")
        # iTunes rate-limits aggressive parallel callers; cap concurrency.
        # Kept low (4) because the catalog is large — a wider fan-out trips the
        # rate limiter and silently drops tracks.
        semaphore = asyncio.Semaphore(4)

        async def _bounded(
            client: httpx.AsyncClient,
            q: str,
            a: str,
            y: int,
            cat: str,
            country: str | None = None,
        ) -> Track | None:
            async with semaphore:
                return await _resolve_track(client, q, a, y, cat, country)

        async with httpx.AsyncClient(timeout=15) as client:
            music_jobs = [
                _bounded(client, q, a, y, "music") for q, a, y in SEED_TRACKS
            ]
            de_jobs = [
                _bounded(client, q, a, y, "music", "DE")
                for q, a, y in SEED_TRACKS_DE
            ]
            film_jobs = [
                _bounded(client, q, a, y, "film_tv")
                for q, a, y in SEED_FILM_TV_TRACKS
            ]
            results = await asyncio.gather(*music_jobs, *de_jobs, *film_jobs)
        self._tracks = [t for t in results if t is not None]
        total = len(SEED_TRACKS) + len(SEED_TRACKS_DE) + len(SEED_FILM_TV_TRACKS)
        log.info("catalog loaded: %d/%d tracks", len(self._tracks), total)
        if not self._tracks:
            raise RuntimeError(
                "catalog empty — iTunes API unreachable or no tracks resolved"
            )
        _save_cache(self._tracks)
        self._merge_community()

    @property
    def tracks(self) -> list[Track]:
        return self._tracks

    def available_categories(self) -> list[str]:
        return sorted({t.category for t in self._tracks})

    def category_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for t in self._tracks:
            counts[t.category] = counts.get(t.category, 0) + 1
        return counts

    def has_seed_track(self, track_id: str) -> bool:
        return any(t.id == track_id for t in self._tracks)


catalog = Catalog()


# ---------- iTunes helpers for player-added songs ----------


# Short-lived cache of in-game search results. Several players often search the
# same popular song around the same time; this dedupes those into one iTunes
# call and rides out brief rate-limit blips. Keyed by normalized query.
_SEARCH_CACHE: dict[str, tuple[float, list[dict[str, str]]]] = {}
_SEARCH_CACHE_TTL_S = 120

# Outbound rate guard for the iTunes Search API. Apple rate-limits to roughly
# 20 requests/min per IP; exceeding it (a burst of player searches) earns the
# server a temporary 403 block. We cap our OWN call rate well under that with a
# token bucket and, when over budget, skip the call (return no results) rather
# than pile on — so the shared server IP can never get blocked, no matter how
# many clients search at once. Cache hits don't consume tokens.
_ITUNES_REFILL_PER_S = 20 / 60.0  # ~20 calls/min sustained (Apple's rough limit)
_ITUNES_BURST = 12.0  # absorbs a handful of simultaneous searches
_itunes_tokens = _ITUNES_BURST
_itunes_last_refill = time.monotonic()


def _itunes_rate_ok() -> bool:
    """Token-bucket gate: True (and consumes a token) if we may call iTunes."""
    global _itunes_tokens, _itunes_last_refill
    now = time.monotonic()
    _itunes_tokens = min(
        _ITUNES_BURST,
        _itunes_tokens + (now - _itunes_last_refill) * _ITUNES_REFILL_PER_S,
    )
    _itunes_last_refill = now
    if _itunes_tokens >= 1.0:
        _itunes_tokens -= 1.0
        return True
    return False


async def itunes_search(query: str, limit: int = 8) -> list[dict[str, str]]:
    """Search iTunes and return slim {track_id, title, artist, preview_url} entries.

    Year and artwork are intentionally omitted so the searching player cannot
    learn information they don't already know about the song; the preview URL is
    included so the player can listen before adding (they already know the song).
    """
    q = query.strip()
    if not q:
        return []

    key = f"{q.lower()}::{limit}"
    cached = _SEARCH_CACHE.get(key)
    if cached is not None and time.time() - cached[0] < _SEARCH_CACHE_TTL_S:
        return cached[1]

    if not _itunes_rate_ok():
        # over our self-imposed budget — skip the call so we never trip Apple's
        # rate limiter and get the server IP blocked for everyone
        log.info("iTunes search rate-capped, skipping %r", q)
        return []

    # Retry on 429/403: a few players searching at once can briefly trip the
    # rate limiter, and returning [] would look like "no results" for a song
    # that clearly exists.
    results: list[Any] = []
    async with httpx.AsyncClient(timeout=10) as client:
        for attempt in range(3):
            try:
                r = await client.get(
                    ITUNES_SEARCH,
                    params={
                        "term": q,
                        "entity": "song",
                        "limit": limit,
                        "country": EXTRA_SONG_STORE,
                    },
                )
                if r.status_code == 403:
                    # hard block — retrying only prolongs it, so bail out quietly
                    log.warning("iTunes search blocked (403) for %r", q)
                    return []
                if r.status_code == 429 and attempt < 2:
                    await asyncio.sleep(0.4 * (2**attempt) + random.uniform(0, 0.2))
                    continue
                r.raise_for_status()
                results = r.json().get("results", [])
                break
            except httpx.HTTPError as e:
                if attempt < 2:
                    await asyncio.sleep(0.4 * (2**attempt) + random.uniform(0, 0.2))
                    continue
                log.warning("iTunes search failed for %r: %s", q, e)
                return []  # transient failure — don't cache it

    out: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for hit in results:
        if hit.get("kind") != "song":
            continue
        if not hit.get("previewUrl"):
            continue
        track_id = str(hit.get("trackId") or "")
        if not track_id or track_id in seen_ids:
            continue
        seen_ids.add(track_id)
        out.append(
            {
                "track_id": track_id,
                "title": clean_title(hit.get("trackName", "")),
                "artist": hit.get("artistName", ""),
                # preview is fine to expose: the player searched for this and
                # already knows the title/artist (no year/artwork leaked)
                "preview_url": hit.get("previewUrl", ""),
            }
        )

    if out:  # cache only real hits, so a transient empty doesn't stick
        if len(_SEARCH_CACHE) > 500:
            _SEARCH_CACHE.clear()
        _SEARCH_CACHE[key] = (time.time(), out)
    return out


# Auto-detect film/TV themes from iTunes metadata: the genre is "Soundtracks"
# (same label in the German store) or the album/collection is clearly a
# soundtrack. Normal songs almost never match these strings, so false positives
# are rare; ambiguous SKUs (covers, concert versions) just stay "music" — the
# safe default, and still better than the old "everything is music".
_FILM_GENRE_RE = re.compile(r"soundtrack|filmmusik", re.IGNORECASE)
_FILM_COLLECTION_RE = re.compile(
    r"soundtrack|motion picture|filmmusik|music from the|original (tv |television )?series",
    re.IGNORECASE,
)


def _detect_category(genre: str, collection: str) -> str:
    if _FILM_GENRE_RE.search(genre or "") or _FILM_COLLECTION_RE.search(
        collection or ""
    ):
        return "film_tv"
    return "music"


async def itunes_lookup_track(track_id: str) -> Track | None:
    """Lookup a single iTunes song by track_id and return a full Track."""
    if not track_id.isdigit():
        return None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                ITUNES_LOOKUP,
                params={
                    "id": track_id,
                    "entity": "song",
                    "country": EXTRA_SONG_STORE,
                },
            )
            r.raise_for_status()
            results = r.json().get("results", [])

            for hit in results:
                if hit.get("kind") != "song":
                    continue
                if not hit.get("previewUrl"):
                    continue
                year_raw = hit.get("releaseDate", "")[:4]
                try:
                    year = int(year_raw)
                except ValueError:
                    continue
                year = await _earliest_release_year(
                    client, hit["trackName"], hit["artistName"], year
                )
                artwork_raw = hit.get("artworkUrl100") or ""
                artwork_url = (
                    artwork_raw.replace("100x100", "600x600")
                    if artwork_raw
                    else None
                )
                category = _detect_category(
                    hit.get("primaryGenreName", ""),
                    hit.get("collectionName", ""),
                )
                return Track(
                    id=f"{EXTRA_TRACK_PREFIX}{track_id}",
                    title=clean_title(hit["trackName"]),
                    artist=hit["artistName"],
                    year=year,
                    preview_url=hit["previewUrl"],
                    artwork_url=artwork_url,
                    category=category,
                )
    except httpx.HTTPError as e:
        log.warning("iTunes lookup failed for %r: %s", track_id, e)
        return None
    return None
