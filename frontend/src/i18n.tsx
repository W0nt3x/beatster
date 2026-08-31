import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react'

export type Lang = 'de' | 'en'

const LANG_KEY = 'hitster:lang'

const en = {
  // shell
  tagline: 'Listen, guess the year, score points.',
  credit: 'Developed with ♥ by Wontex · Headless Ape Studios',
  pageNotFound: 'Page not found',
  backToLanding: 'Back to landing',

  // landing
  createRoom: 'Create room',
  creatingRoom: 'Creating room…',
  singleplayer: 'Singleplayer vs. AI',
  orJoinExisting: 'or join existing',

  // leaderboard
  leaderboard: 'Leaderboard',
  lbPlayer: 'Player',
  lbWins: 'Wins',
  lbGames: 'Games',
  lbStealsTitle: 'Cards stolen',
  lbLoading: 'Loading…',
  lbEmpty: 'No games recorded yet — stats count from now on. Go play one!',
  lbGamesRecorded: (n: number) =>
    `${n} multiplayer game${n === 1 ? '' : 's'} recorded`,
  roomCodePlaceholder: 'ROOM CODE',
  join: 'Join',

  // name prompt
  whatsYourName: "What's your name?",
  pickName: 'Pick a name your friends will recognize.',
  yourName: 'Your name',
  cancel: 'Cancel',

  // connection
  joiningRoom: (code: string) => `Joining room ${code}…`,
  connectingRoom: (code: string) => `Connecting to room ${code}…`,
  roomNotFound: (code: string) => `Room ${code} not found.`,
  reconnecting: 'Reconnecting…',
  audioBlocked:
    'Audio was blocked by your browser. Click anywhere on the page, then ask the host to restart the round.',

  // room header
  roomLabel: 'Room',
  copyInvite: 'Copy invite link',
  copied: 'Copied!',
  showQr: 'Show QR code',
  scanToJoin: 'Scan to join',
  close: 'Close',
  leaveRoom: 'Leave room',
  volume: 'Audio volume',

  // player list
  players: 'Players',
  youSuffix: '(you)',
  hostBadge: 'host',
  spectatorBadge: 'spectator',
  offlineBadge: 'offline',
  botBadge: 'bot',
  aiOpponents: 'AI opponents',
  addBot: 'Add bot',
  botEasy: 'Easy',
  botMedium: 'Medium',
  botHard: 'Hard',
  currentTurnAria: 'current turn',
  kickedTitle: 'You were removed',
  kickedBody: 'The host removed you from this room.',
  updateAvailable: 'A new version is available.',
  reloadNow: 'Reload',
  manageAria: (name: string) => `Manage ${name}`,
  cardWord: 'card',
  kickAction: 'Remove',
  abortGame: 'Abort game',
  abortConfirm: 'Abort the game and send everyone back to the lobby?',

  // lobby
  gameSettings: 'Game settings',
  cardsToWin: 'Cards to win',
  songsPerPlayer: 'Songs per player',
  moreSettings: 'More settings',
  timingLabel: 'Timing (sec)',
  snippetLabel: 'Snippet',
  guessLabel: 'Guess',
  stealLabel: 'Steal',
  startingCards: 'Starting cards',
  audioOutput: 'Sound',
  audioCouch: 'Couch',
  audioOnline: 'Online',
  audioModeHint:
    "Couch: only your device plays the sound. Online: every player's device plays.",
  audioOnHost: "Sound plays on the host's device.",
  categoriesLabel: 'Categories',
  categoryMusic: 'Music',
  categoryFilmTv: 'Film & TV',
  tracksInPool: (n: number) => `${n} track${n === 1 ? '' : 's'} in pool`,
  playerAddedOnlySuffix: ' (player-added only)',
  startGame: 'Start game',
  waitingHostStartGame: 'Waiting for the host to start the game…',

  // lobby — neon rebuild
  roomCodeLabel: 'Room code',
  inviteFriends: 'Invite friends',
  invite: 'Invite',
  copyLink: 'Copy link',
  modeClassic: 'Classic',
  modeClassicSub: 'Timeline · collect cards',
  modeBingo: 'Bingo',
  modeBingoSub: '5 categories · 5×5 card',
  comingSoon: 'Soon',
  settingsChip: 'Settings',
  avatarTitle: 'Pick your avatar',
  avatarReroll: 'Reroll',
  avatarCustomSection: 'Your images',
  sectionGame: 'Game',
  sectionSoundRules: 'Sound & rules',
  chipCards: (n: number) => `${n} cards`,
  addSongCta: 'Add a song',
  hideSongSearch: 'Hide song search',

  // song pool
  songPool: 'Song pool',
  poolStats: (total: number, yours: number, cap: number) =>
    `${total} added · you ${yours}/${cap}`,
  poolStatsUnlimited: (total: number, yours: number) =>
    `${total} added · you ${yours}`,
  onlyPlayerAddedToggle: 'Use only player-added songs',
  contributionsDisabled:
    'The host has disabled adding songs (limit set to 0).',
  overCap: (used: number, cap: number) =>
    `You're over the limit (${used}/${cap}). Remove some below.`,
  allSlotsUsed: (cap: number) => `You've used all ${cap} of your slots.`,
  searchSong: 'Search a song…',
  searchButton: 'Search',
  searching: 'Searching…',
  noMatches: 'No matches.',
  add: 'Add',
  slotsRemaining: (n: number) => `${n} slot${n === 1 ? '' : 's'} remaining`,
  yourContributions: (n: number) => `Your contributions (${n})`,
  remove: 'Remove',
  tapToChangeCategory: 'Tap to switch between Music and Film/TV',
  playPreview: 'Play preview',
  pausePreview: 'Pause preview',

  // listening / placing
  nowPlaying: 'Now playing',
  snippetSeconds: (s: number) => `${s}-second snippet`,
  timeRemaining: 'Time remaining',

  // reveal
  noCover: 'no cover',
  coverAlt: (title: string) => `${title} cover art`,
  addedByLabel: 'Added by',
  releasedIn: 'Released in',
  finalScoreboard: 'Final scoreboard',
  waitingHostScoreboard: 'Waiting for the host to show the final scoreboard…',

  // gameplay
  pickingFirst: 'Picking who goes first',
  youStartGame: 'You start the game',
  startsGame: 'starts the game',
  yourTurn: 'Your turn',
  playersTurn: (name: string) => `${name}'s turn`,
  yourTimeline: 'Your timeline',
  playersTimeline: (name: string) => `${name}'s timeline`,
  placeSong: 'Place the song',
  pickWhereFits: 'Pick where it fits',
  isPlacing: (name: string) => `${name} is placing…`,
  beforeYear: (y: number) => `Before ${y}`,
  afterYear: (y: number) => `After ${y}`,
  betweenYears: (a: number, b: number) => `Between ${a} and ${b}`,
  gotItRight: (name: string) => `${name} got it right!`,
  placedWrong: (name: string) => `${name} placed it wrong.`,
  locksPlace: (name: string, place: number) =>
    `${name} locks in place ${place}!`,
  nextTurn: 'Next turn',
  waitingHostNextTurn: 'Waiting for the host to start the next turn…',
  poolExhausted: 'No fresh songs left in the pool — the game ends here',
  unknownPlayer: 'Unknown',

  // steal
  stealToggle: 'Allow stealing',
  stealHint:
    'When the active player guesses wrong, everyone else races to place the card on their own timeline — first correct steal takes it.',
  stealEyebrow: 'Steal!',
  stealMissedYou: 'You missed!',
  stealMissedOther: (name: string) => `${name} missed!`,
  stealPrompt: 'Quick — where does it go on your timeline?',
  stealLockedIn: 'Placed — waiting for the result…',
  stealMisserWatch: 'You missed — the others can steal it now.',
  stealWatching: 'The others are racing to steal it…',
  stealPlaceOnTimeline: 'Place it on your timeline',
  stealWon: (name: string) => `${name} stole the card!`,
  stealNobody: 'Nobody stole it.',

  // game over
  gameOver: 'Game over',
  winsWith: (count: number, score: number) =>
    `${count > 1 ? 'win' : 'wins'} with ${score} ${score === 1 ? 'card' : 'cards'}`,
  noPointsScored: 'No points scored',
  rematch: 'Rematch',
  waitingHostRematch: 'Waiting for the host to start a rematch…',

  // bingo mode
  bingo: {
    categoriesLabel: 'Bingo categories',
    pickFive: 'Pick exactly 5 — each takes one of the board colours',
    presetBeginner: 'Beginner',
    presetAdvanced: 'Advanced',
    answerTime: 'Answer time',
    round: (n: number) => `Round ${n}`,
    spinning: 'Spinning…',
    categoryIs: 'Category',
    cat: {
      year1: 'Year ±1',
      year2: 'Year ±2',
      year3: 'Year ±3',
      year4: 'Year ±4',
      year5: 'Year ±5',
      decade: 'Decade',
      before1990: 'Before 1990?',
      before2000: 'Before 2000?',
      before2010: 'Before 2010?',
      exact: 'Exact year',
      artist: 'Name the artist',
      title: 'Name the song',
      anytext: 'Artist or song',
      prevsong: 'Time duel',
      closest: 'Closest wins',
    },
    promptYear: (tol: number) => `Which year? ±${tol} counts`,
    promptExact: 'Which year? Only the exact one counts',
    promptDecade: 'Which decade?',
    decadeName: (d: number) => `${d}s`,
    promptBefore: (y: number) => `Before ${y} — or ${y} and later?`,
    beforeBtn: (y: number) => `Before ${y}`,
    afterBtn: (y: number) => `${y} or later`,
    promptArtist: "Who's singing?",
    promptTitle: "What's the song called?",
    promptAny: 'Artist or song title — either counts',
    promptPrev: (title: string, year: number) =>
      `Older or newer than “${title}” (${year})?`,
    promptPrevGeneric: 'Older or newer than the last song?',
    olderBtn: 'Older',
    newerBtn: 'Newer',
    promptClosest: 'Which year? The closest guess takes the mark',
    yearPlaceholder: 'Year…',
    textPlaceholder: 'Your answer…',
    submit: 'Lock in',
    submitted: 'Locked in — you can still change it',
    answeredCount: (n: number, total: number) => `${n}/${total} answered`,
    itWas: 'It was',
    yourAnswer: 'Your answer',
    correctBadge: 'right',
    wrongBadge: 'wrong',
    exactBadge: 'exact!',
    markPrompt: 'Pick a matching cell on your card',
    markWaiting: (n: number) =>
      n === 1 ? 'Waiting for 1 player to mark…' : `Waiting for ${n} players to mark…`,
    erasePrompt: 'Exact hit! Erase one opponent mark — tap it on their card',
    erasePass: 'Skip the erase',
    yourCard: 'Your card',
    cardOf: (name: string) => `${name}'s card`,
    bingoWin: 'BINGO!',
    winsGame: (names: string, n: number) =>
      n > 1 ? `${names} take the bingo!` : `${names} takes the bingo!`,
    bingoWinsWith: (count: number, marks: number) =>
      `${count > 1 ? 'win' : 'wins'} with ${marks} mark${marks === 1 ? '' : 's'}`,
    cellAria: (row: number, col: number) => `Row ${row}, column ${col}`,
  },

  // how to play
  howToPlay: {
    title: 'How to play',
    back: 'Back',
    next: 'Next',
    got: 'Got it',
    modeClassic: 'Classic',
    modeBingo: 'Bingo',
    listenTitle: 'Listen',
    listenBody: 'A mystery song plays for 15 seconds — no title, no year shown.',
    placeTitle: 'Place',
    placeBody:
      'Is it older or newer than the songs you already have? Drop it in the right gap by year.',
    collectTitle: 'Collect',
    collectBody:
      'Land it right and the card is yours. First to the card target wins.',
    slotBefore: 'before',
    slotBetween: 'between',
    slotAfter: 'after',
    difficultyNote:
      'Every card you win adds another gap to judge — so each turn gets a little harder.',
    bingoSpinTitle: 'Spin & listen',
    bingoSpinBody:
      'The wheel picks one of the 5 categories and a song plays — everyone answers at the same time.',
    bingoMarkTitle: 'Mark',
    bingoMarkBody:
      "Answered right? Mark one free cell of the category's colour on your 5×5 card — which one is your strategy.",
    bingoWinTitle: 'BINGO!',
    bingoWinBody: 'The first full row, column or diagonal wins the game.',
    bingoEraseNote:
      'Hit the exact year on a ±category and you get to erase one mark on an opponent\'s card.',
  },
}

export type Messages = typeof en

const de: Messages = {
  // shell
  tagline: 'Hören, Jahr raten, Punkte sammeln.',
  credit: 'Mit ♥ entwickelt von Wontex · Headless Ape Studios',
  pageNotFound: 'Seite nicht gefunden',
  backToLanding: 'Zur Startseite',

  // landing
  createRoom: 'Raum erstellen',
  creatingRoom: 'Raum wird erstellt…',
  singleplayer: 'Einzelspieler gegen KI',
  orJoinExisting: 'oder einem Raum beitreten',

  // leaderboard
  leaderboard: 'Bestenliste',
  lbPlayer: 'Spieler',
  lbWins: 'Siege',
  lbGames: 'Spiele',
  lbStealsTitle: 'Geklaute Karten',
  lbLoading: 'Lädt…',
  lbEmpty:
    'Noch keine Spiele aufgezeichnet — ab jetzt zählen die Stats. Spielt eins!',
  lbGamesRecorded: (n) =>
    n === 1 ? '1 Multiplayer-Spiel aufgezeichnet' : `${n} Multiplayer-Spiele aufgezeichnet`,
  roomCodePlaceholder: 'RAUMCODE',
  join: 'Beitreten',

  // name prompt
  whatsYourName: 'Wie heißt du?',
  pickName: 'Wähl einen Namen, den deine Freunde erkennen.',
  yourName: 'Dein Name',
  cancel: 'Abbrechen',

  // connection
  joiningRoom: (code) => `Trete Raum ${code} bei…`,
  connectingRoom: (code) => `Verbinde mit Raum ${code}…`,
  roomNotFound: (code) => `Raum ${code} wurde nicht gefunden.`,
  reconnecting: 'Verbindung wird wiederhergestellt…',
  audioBlocked:
    'Dein Browser hat die Audio-Wiedergabe blockiert. Klick irgendwo auf die Seite und bitte den Host, die Runde neu zu starten.',

  // room header
  roomLabel: 'Raum',
  copyInvite: 'Einladungslink kopieren',
  copied: 'Kopiert!',
  showQr: 'QR-Code zeigen',
  scanToJoin: 'Zum Beitreten scannen',
  close: 'Schließen',
  leaveRoom: 'Raum verlassen',
  volume: 'Lautstärke',

  // player list
  players: 'Spieler',
  youSuffix: '(du)',
  hostBadge: 'Host',
  spectatorBadge: 'Zuschauer',
  offlineBadge: 'offline',
  botBadge: 'Bot',
  aiOpponents: 'KI-Gegner',
  addBot: 'Bot hinzufügen',
  botEasy: 'Leicht',
  botMedium: 'Mittel',
  botHard: 'Schwer',
  currentTurnAria: 'ist am Zug',
  kickedTitle: 'Du wurdest entfernt',
  kickedBody: 'Der Host hat dich aus diesem Raum entfernt.',
  updateAvailable: 'Neue Version verfügbar.',
  reloadNow: 'Neu laden',
  manageAria: (name) => `${name} verwalten`,
  cardWord: 'Karte',
  kickAction: 'Entfernen',
  abortGame: 'Spiel abbrechen',
  abortConfirm: 'Spiel abbrechen und alle zurück in die Lobby schicken?',

  // lobby
  gameSettings: 'Spieleinstellungen',
  cardsToWin: 'Karten zum Sieg',
  songsPerPlayer: 'Songs pro Spieler',
  moreSettings: 'Mehr Einstellungen',
  timingLabel: 'Zeiten (Sek.)',
  snippetLabel: 'Snippet',
  guessLabel: 'Raten',
  stealLabel: 'Klauen',
  startingCards: 'Startkarten',
  audioOutput: 'Ton',
  audioCouch: 'Couch',
  audioOnline: 'Online',
  audioModeHint:
    'Couch: nur dein Gerät spielt den Ton. Online: jedes Gerät spielt.',
  audioOnHost: 'Der Ton läuft über das Host-Gerät.',
  categoriesLabel: 'Kategorien',
  categoryMusic: 'Musik',
  categoryFilmTv: 'Film & TV',
  tracksInPool: (n) => `${n} Song${n === 1 ? '' : 's'} im Pool`,
  playerAddedOnlySuffix: ' (nur von Spielern hinzugefügt)',
  startGame: 'Spiel starten',
  waitingHostStartGame: 'Warten, bis der Host das Spiel startet…',

  // lobby — neon rebuild
  roomCodeLabel: 'Raumcode',
  inviteFriends: 'Freunde einladen',
  invite: 'Einladen',
  copyLink: 'Link kopieren',
  modeClassic: 'Klassisch',
  modeClassicSub: 'Timeline · Karten sammeln',
  modeBingo: 'Bingo',
  modeBingoSub: '5 Kategorien · 5×5-Karte',
  comingSoon: 'Bald',
  settingsChip: 'Einstellungen',
  avatarTitle: 'Wähl deinen Avatar',
  avatarReroll: 'Neu würfeln',
  avatarCustomSection: 'Eure Bilder',
  sectionGame: 'Spiel',
  sectionSoundRules: 'Sound & Regeln',
  chipCards: (n) => `${n} Karten`,
  addSongCta: 'Song hinzufügen',
  hideSongSearch: 'Suche ausblenden',

  // song pool
  songPool: 'Song-Pool',
  poolStats: (total, yours, cap) =>
    `${total} hinzugefügt · du ${yours}/${cap}`,
  poolStatsUnlimited: (total, yours) =>
    `${total} hinzugefügt · du ${yours}`,
  onlyPlayerAddedToggle: 'Nur von Spielern hinzugefügte Songs verwenden',
  contributionsDisabled:
    'Der Host hat das Hinzufügen von Songs deaktiviert (Limit auf 0).',
  overCap: (used, cap) =>
    `Du bist über dem Limit (${used}/${cap}). Entferne unten ein paar Songs.`,
  allSlotsUsed: (cap) => `Du hast alle ${cap} Plätze belegt.`,
  searchSong: 'Song suchen…',
  searchButton: 'Suchen',
  searching: 'Suche…',
  noMatches: 'Keine Treffer.',
  add: 'Hinzufügen',
  slotsRemaining: (n) =>
    n === 1 ? 'Noch 1 Platz frei' : `Noch ${n} Plätze frei`,
  yourContributions: (n) => `Deine Songs (${n})`,
  remove: 'Entfernen',
  tapToChangeCategory: 'Tippen, um zwischen Musik und Film/TV zu wechseln',
  playPreview: 'Vorschau abspielen',
  pausePreview: 'Vorschau pausieren',

  // listening / placing
  nowPlaying: 'Läuft gerade',
  snippetSeconds: (s) => `${s}-Sekunden-Ausschnitt`,
  timeRemaining: 'Verbleibende Zeit',

  // reveal
  noCover: 'kein Cover',
  coverAlt: (title) => `Cover von ${title}`,
  addedByLabel: 'Hinzugefügt von',
  releasedIn: 'Erschienen',
  finalScoreboard: 'Endstand',
  waitingHostScoreboard: 'Warten, bis der Host den Endstand zeigt…',

  // gameplay
  pickingFirst: 'Wer fängt an?',
  youStartGame: 'Du fängst an',
  startsGame: 'fängt an',
  yourTurn: 'Du bist dran',
  playersTurn: (name) => `${name} ist dran`,
  yourTimeline: 'Deine Timeline',
  playersTimeline: (name) => `Timeline von ${name}`,
  placeSong: 'Platziere den Song',
  pickWhereFits: 'Wähl die richtige Stelle',
  isPlacing: (name) => `${name} platziert…`,
  beforeYear: (y) => `Vor ${y}`,
  afterYear: (y) => `Nach ${y}`,
  betweenYears: (a, b) => `Zwischen ${a} und ${b}`,
  gotItRight: (name) => `${name} hat richtig gelegen!`,
  placedWrong: (name) => `${name} hat daneben gelegen.`,
  locksPlace: (name, place) => `${name} sichert sich Platz ${place}!`,
  nextTurn: 'Nächster Zug',
  waitingHostNextTurn: 'Warten, bis der Host den nächsten Zug startet…',
  poolExhausted: 'Keine neuen Songs mehr im Pool — hier endet das Spiel',
  unknownPlayer: 'Unbekannt',

  // steal
  stealToggle: 'Klauen erlauben',
  stealHint:
    'Liegt der aktive Spieler daneben, dürfen alle anderen die Karte auf ihrer eigenen Timeline platzieren — der erste richtige Klau schnappt sie sich.',
  stealEyebrow: 'Klauen!',
  stealMissedYou: 'Daneben!',
  stealMissedOther: (name) => `${name} lag daneben!`,
  stealPrompt: 'Schnell — wo gehört er auf deine Timeline?',
  stealLockedIn: 'Platziert — warte auf die Auflösung…',
  stealMisserWatch: 'Daneben — die anderen können jetzt klauen.',
  stealWatching: 'Die anderen versuchen zu klauen…',
  stealPlaceOnTimeline: 'Platziere ihn auf deiner Timeline',
  stealWon: (name) => `${name} hat die Karte geklaut!`,
  stealNobody: 'Niemand hat geklaut.',

  // game over
  gameOver: 'Spiel vorbei',
  winsWith: (count, score) =>
    `${count > 1 ? 'gewinnen' : 'gewinnt'} mit ${score} ${score === 1 ? 'Karte' : 'Karten'}`,
  noPointsScored: 'Keine Punkte erzielt',
  rematch: 'Revanche',
  waitingHostRematch: 'Warten, bis der Host eine Revanche startet…',

  // bingo mode
  bingo: {
    categoriesLabel: 'Bingo-Kategorien',
    pickFive: 'Wähl genau 5 — jede bekommt eine der Brett-Farben',
    presetBeginner: 'Anfänger',
    presetAdvanced: 'Fortgeschritten',
    answerTime: 'Antwortzeit',
    round: (n) => `Runde ${n}`,
    spinning: 'Das Rad dreht…',
    categoryIs: 'Kategorie',
    cat: {
      year1: 'Jahr ±1',
      year2: 'Jahr ±2',
      year3: 'Jahr ±3',
      year4: 'Jahr ±4',
      year5: 'Jahr ±5',
      decade: 'Jahrzehnt',
      before1990: 'Vor 1990?',
      before2000: 'Vor 2000?',
      before2010: 'Vor 2010?',
      exact: 'Exaktes Jahr',
      artist: 'Künstler nennen',
      title: 'Titel nennen',
      anytext: 'Künstler oder Titel',
      prevsong: 'Zeitduell',
      closest: 'Wettschätzen',
    },
    promptYear: (tol) => `Welches Jahr? ±${tol} zählt`,
    promptExact: 'Welches Jahr? Nur exakt zählt',
    promptDecade: 'Welches Jahrzehnt?',
    decadeName: (d) => `${d}er`,
    promptBefore: (y) => `Vor ${y} — oder ${y} und später?`,
    beforeBtn: (y) => `Vor ${y}`,
    afterBtn: (y) => `${y} oder später`,
    promptArtist: 'Wer singt das?',
    promptTitle: 'Wie heißt der Song?',
    promptAny: 'Künstler oder Titel — eins reicht',
    promptPrev: (title, year) =>
      `Älter oder neuer als „${title}“ (${year})?`,
    promptPrevGeneric: 'Älter oder neuer als der letzte Song?',
    olderBtn: 'Älter',
    newerBtn: 'Neuer',
    promptClosest: 'Welches Jahr? Wer am nächsten dran ist, kreuzt an',
    yearPlaceholder: 'Jahr…',
    textPlaceholder: 'Deine Antwort…',
    submit: 'Einloggen',
    submitted: 'Eingeloggt — du kannst noch ändern',
    answeredCount: (n, total) => `${n}/${total} haben geantwortet`,
    itWas: 'Das war',
    yourAnswer: 'Deine Antwort',
    correctBadge: 'richtig',
    wrongBadge: 'falsch',
    exactBadge: 'exakt!',
    markPrompt: 'Wähl ein passendes Feld auf deiner Karte',
    markWaiting: (n) =>
      n === 1 ? 'Warte auf 1 Spieler…' : `Warte auf ${n} Spieler…`,
    erasePrompt:
      'Exakt getroffen! Radiere ein Kreuz — tipp es auf einer Gegner-Karte an',
    erasePass: 'Nicht radieren',
    yourCard: 'Deine Karte',
    cardOf: (name) => `Karte von ${name}`,
    bingoWin: 'BINGO!',
    winsGame: (names, n) =>
      n > 1 ? `${names} holen das Bingo!` : `${names} holt das Bingo!`,
    bingoWinsWith: (count, marks) =>
      `${count > 1 ? 'gewinnen' : 'gewinnt'} mit ${marks} ${marks === 1 ? 'Kreuz' : 'Kreuzen'}`,
    cellAria: (row, col) => `Reihe ${row}, Spalte ${col}`,
  },

  // how to play
  howToPlay: {
    title: 'So wird gespielt',
    back: 'Zurück',
    next: 'Weiter',
    got: "Los geht's",
    modeClassic: 'Classic',
    modeBingo: 'Bingo',
    listenTitle: 'Zuhören',
    listenBody: 'Ein Mystery-Song spielt 15 Sekunden — ohne Titel, ohne Jahr.',
    placeTitle: 'Einordnen',
    placeBody:
      'Älter oder neuer als deine Karten? Schieb ihn nach Jahr in die richtige Lücke.',
    collectTitle: 'Sammeln',
    collectBody:
      'Richtig platziert? Die Karte gehört dir. Wer zuerst das Ziel erreicht, gewinnt.',
    slotBefore: 'davor',
    slotBetween: 'dazwischen',
    slotAfter: 'danach',
    difficultyNote:
      'Jede gewonnene Karte bringt eine Lücke mehr — so wird jede Runde etwas schwerer.',
    bingoSpinTitle: 'Rad & Song',
    bingoSpinBody:
      'Das Rad wählt eine der 5 Kategorien und ein Song spielt an — alle antworten gleichzeitig.',
    bingoMarkTitle: 'Ankreuzen',
    bingoMarkBody:
      'Richtig geantwortet? Kreuze ein freies Feld in der Farbe der Kategorie auf deiner 5×5-Karte an — welches, ist deine Taktik.',
    bingoWinTitle: 'BINGO!',
    bingoWinBody: 'Die erste volle Reihe, Spalte oder Diagonale gewinnt das Spiel.',
    bingoEraseNote:
      'Exaktes Jahr bei einer ±Kategorie getroffen? Dann darfst du ein Kreuz auf einer Gegner-Karte wegradieren.',
  },
}

const messages: Record<Lang, Messages> = { de, en }

export function resolveInitialLang(): Lang {
  const stored = localStorage.getItem(LANG_KEY)
  if (stored === 'de' || stored === 'en') return stored
  return navigator.language.toLowerCase().startsWith('de') ? 'de' : 'en'
}

type I18nValue = {
  lang: Lang
  setLang: (l: Lang) => void
  t: Messages
}

const I18nContext = createContext<I18nValue | null>(null)

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>(resolveInitialLang)

  useEffect(() => {
    localStorage.setItem(LANG_KEY, lang)
    document.documentElement.lang = lang
  }, [lang])

  return (
    <I18nContext.Provider value={{ lang, setLang, t: messages[lang] }}>
      {children}
    </I18nContext.Provider>
  )
}

export function useI18n(): I18nValue {
  const v = useContext(I18nContext)
  if (!v) throw new Error('useI18n must be used inside <I18nProvider>')
  return v
}
