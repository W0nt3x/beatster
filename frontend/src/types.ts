export type RoomState =
  | 'lobby'
  | 'hitster_intro'
  | 'hitster_listening'
  | 'hitster_placing'
  | 'hitster_stealing'
  | 'hitster_reveal'
  | 'bingo_spin'
  | 'bingo_answering'
  | 'bingo_reveal'
  | 'game_over'

export type AudioMode = 'online' | 'couch'

export type GameMode = 'classic' | 'bingo'

export type BingoPlayerResult = {
  player_id: string
  answer: string
  correct: boolean
  exact: boolean
}

export type BingoRoundResultMsg = {
  type: 'bingo_round_result'
  round: number
  category_index: number
  card: CardSnapshot
  results: BingoPlayerResult[]
  mark_deadline_ms: number | null
  mark_pending: string[]
  erase_pending: string[]
}

export type CardSnapshot = {
  track_id: string
  title: string
  artist: string
  year: number
  artwork_url: string | null
  added_by: string | null
}

export type PlacementResultMsg = {
  type: 'placement_result'
  placer_id: string
  slot_index: number | null
  correct: boolean
  card: CardSnapshot
  placer_new_hand: CardSnapshot[]
  card_counts: Record<string, number>
  placer_finished_place: number | null
  finished_players: string[]
  game_finished: boolean
  pool_exhausted: boolean
  steal_offered: boolean
  stolen_by: string | null
  stealer_new_hand: CardSnapshot[] | null
  stealer_finished_place: number | null
}

export type Player = {
  id: string
  name: string
  is_bot: boolean
  // "style:seed" (DiceBear) or "img:<file>" (bundled catalog); "" = default
  avatar: string
}

export type ExtraTrackSummary = {
  track_id: string
  title: string
  artist: string
  category: string
  preview_url: string
}

export type RoomSnapshot = {
  state: RoomState
  players: Player[]
  host_id: string | null
  cumulative_scores: Record<string, number>
  disconnected: string[]
  category_filter: string[]
  available_categories: string[]
  category_counts: Record<string, number>
  extra_tracks_total: number
  per_player_cap: number
  effective_pool_size: number
  your_extra_tracks: ExtraTrackSummary[]
  only_player_added: boolean
  card_target: number
  audio_mode: AudioMode
  steal_enabled: boolean
  snippet_duration_s: number
  placing_seconds: number
  steal_seconds: number
  starting_cards: number
  hands: Record<string, CardSnapshot[]>
  turn_order: string[]
  finished_players: string[]
  current_turn_player_id: string | null
  last_placement_result: PlacementResultMsg | null
  current_preview_url: string | null
  placing_deadline_ms: number | null
  steal_placer_id: string | null
  steal_deadline_ms: number | null
  steal_attempted: string[]
  game_mode: GameMode
  bingo_categories: string[]
  bingo_answer_seconds: number
  bingo_cards: Record<string, number[]>
  bingo_marks: Record<string, number[]>
  bingo_round: number
  bingo_category_index: number | null
  bingo_prev_title: string | null
  bingo_prev_year: number | null
  bingo_deadline_ms: number | null
  bingo_answered: string[]
  bingo_mark_pending: string[]
  bingo_erase_pending: string[]
  last_bingo_result: BingoRoundResultMsg | null
  bingo_winners: string[]
  promo_active: boolean
  promo_by: string | null
}

export type ServerMsg =
  | { type: 'joined'; player_id: string; room_code: string; snapshot: RoomSnapshot }
  | { type: 'player_joined'; player: Player }
  | { type: 'player_left'; player_id: string }
  | { type: 'player_kicked'; player_id: string }
  | {
      type: 'cards_adjusted'
      player_id: string
      hand: CardSnapshot[]
      card_counts: Record<string, number>
    }
  | { type: 'host_changed'; host_id: string }
  | {
      type: 'connection_changed'
      disconnected: string[]
      host_id: string | null
    }
  | { type: 'placing_phase'; deadline_ms: number }
  | { type: 'only_player_added_changed'; only: boolean }
  | { type: 'extra_tracks_total_changed'; extra_tracks_total: number; per_player_cap: number; effective_pool_size: number }
  | { type: 'your_extra_tracks_changed'; your_extra_tracks: ExtraTrackSummary[] }
  | { type: 'category_filter_changed'; categories: string[] }
  | { type: 'card_target_changed'; card_target: number }
  | {
      type: 'round_settings_changed'
      snippet_duration_s: number
      placing_seconds: number
      steal_seconds: number
      starting_cards: number
    }
  | { type: 'audio_mode_changed'; mode: AudioMode }
  | { type: 'steal_enabled_changed'; enabled: boolean }
  | { type: 'steal_started'; placer_id: string; deadline_ms: number }
  | { type: 'steal_attempted'; player_id: string }
  | { type: 'hitster_game_started'; turn_order: string[]; hands: Record<string, CardSnapshot[]> }
  | { type: 'hitster_turn_changed'; current_turn_player_id: string; preview_url: string; snippet_duration_s: number }
  | PlacementResultMsg
  | { type: 'game_mode_changed'; mode: GameMode }
  | { type: 'bingo_settings_changed'; categories: string[]; answer_seconds: number }
  | {
      type: 'bingo_game_started'
      participants: string[]
      cards: Record<string, number[]>
      categories: string[]
    }
  | {
      type: 'bingo_spin'
      round: number
      category_index: number
      prev_title: string | null
      prev_year: number | null
    }
  | { type: 'bingo_answering'; deadline_ms: number; preview_url: string }
  | { type: 'bingo_answered'; player_id: string; answered: string[] }
  | BingoRoundResultMsg
  | {
      type: 'bingo_marks_changed'
      player_id: string | null
      marks: number[] | null
      actor_id: string | null
      erased: boolean
      card_counts: Record<string, number>
      mark_pending: string[]
      erase_pending: string[]
    }
  | {
      type: 'bingo_round_done'
      marks: Record<string, number[]>
      card_counts: Record<string, number>
      winners: string[]
    }
  | { type: 'game_over'; cumulative_scores: Record<string, number>; finished_players: string[] }
  | { type: 'rematch_started' }
  | { type: 'promo_state'; active: boolean; triggered_by: string | null }
  | { type: 'avatar_changed'; player_id: string; avatar: string }
  | { type: 'error'; message: string }

export type ClientMsg =
  | { type: 'join'; name: string; player_id: string | null; avatar: string }
  | { type: 'set_avatar'; avatar: string }
  | { type: 'start_round' }
  | { type: 'set_category_filter'; categories: string[] }
  | { type: 'set_only_player_added'; only: boolean }
  | { type: 'set_card_target'; card_target: number }
  | { type: 'set_songs_per_player'; songs_per_player: number }
  | { type: 'set_snippet_duration'; seconds: number }
  | { type: 'set_placing_seconds'; seconds: number }
  | { type: 'set_steal_seconds'; seconds: number }
  | { type: 'set_starting_cards'; count: number }
  | { type: 'set_audio_mode'; mode: AudioMode }
  | { type: 'set_steal_enabled'; enabled: boolean }
  | { type: 'set_game_mode'; mode: GameMode }
  | { type: 'set_bingo_categories'; categories: string[] }
  | { type: 'set_bingo_answer_seconds'; seconds: number }
  | { type: 'bingo_answer'; value: string }
  | { type: 'bingo_mark'; cell: number }
  | { type: 'bingo_erase'; target_id: string | null; cell: number | null }
  | { type: 'steal_place'; slot_index: number }
  | { type: 'set_promo'; active: boolean }
  | { type: 'place_song'; slot_index: number }
  | { type: 'add_song'; track_id: string }
  | { type: 'remove_song'; track_id: string }
  | { type: 'set_song_category'; track_id: string; category: string }
  | { type: 'add_bot'; difficulty: string }
  | { type: 'kick_player'; target_id: string }
  | { type: 'give_card'; target_id: string }
  | { type: 'take_card'; target_id: string }
  | { type: 'abort_to_lobby' }
  | { type: 'end_game' }
  | { type: 'rematch' }
