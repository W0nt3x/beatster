// Pure reducer: applies a server broadcast to the room snapshot. Kept
// separate from the socket lifecycle so it stays trivially testable.
import type { RoomSnapshot, ServerMsg } from './types'

export function applyMsg(s: RoomSnapshot, msg: ServerMsg): RoomSnapshot {
  switch (msg.type) {
    case 'player_joined':
      if (s.players.some((p) => p.id === msg.player.id)) return s
      return {
        ...s,
        players: [...s.players, msg.player],
        cumulative_scores: {
          [msg.player.id]: 0,
          ...s.cumulative_scores,
        },
      }
    case 'player_left':
      return {
        ...s,
        players: s.players.filter((p) => p.id !== msg.player_id),
      }
    case 'avatar_changed':
      return {
        ...s,
        players: s.players.map((p) =>
          p.id === msg.player_id ? { ...p, avatar: msg.avatar } : p,
        ),
      }
    case 'host_changed':
      return { ...s, host_id: msg.host_id }
    case 'connection_changed':
      return { ...s, disconnected: msg.disconnected, host_id: msg.host_id }
    case 'placing_phase':
      return {
        ...s,
        state: 'classic_placing',
        placing_deadline_ms: msg.deadline_ms,
      }
    case 'only_player_added_changed':
      return { ...s, only_player_added: msg.only }
    case 'extra_tracks_total_changed':
      return {
        ...s,
        extra_tracks_total: msg.extra_tracks_total,
        per_player_cap: msg.per_player_cap,
        effective_pool_size: msg.effective_pool_size,
      }
    case 'category_filter_changed':
      return { ...s, category_filter: msg.categories }
    case 'your_extra_tracks_changed':
      return { ...s, your_extra_tracks: msg.your_extra_tracks }
    case 'card_target_changed':
      return { ...s, card_target: msg.card_target }
    case 'round_settings_changed':
      return {
        ...s,
        snippet_duration_s: msg.snippet_duration_s,
        placing_seconds: msg.placing_seconds,
        steal_seconds: msg.steal_seconds,
        starting_cards: msg.starting_cards,
      }
    case 'audio_mode_changed':
      return { ...s, audio_mode: msg.mode }
    case 'steal_enabled_changed':
      return { ...s, steal_enabled: msg.enabled }
    case 'steal_started':
      return {
        ...s,
        state: 'classic_stealing',
        steal_placer_id: msg.placer_id,
        steal_deadline_ms: msg.deadline_ms,
        steal_attempted: [],
        current_preview_url: null,
        placing_deadline_ms: null,
      }
    case 'steal_attempted':
      return s.steal_attempted.includes(msg.player_id)
        ? s
        : { ...s, steal_attempted: [...s.steal_attempted, msg.player_id] }
    case 'classic_game_started': {
      const counts = Object.fromEntries(
        Object.entries(msg.hands).map(([pid, h]) => [pid, h.length]),
      )
      return {
        ...s,
        state: 'classic_intro',
        turn_order: msg.turn_order,
        hands: msg.hands,
        cumulative_scores: counts,
        current_turn_player_id: msg.turn_order[0] ?? null,
        last_placement_result: null,
      }
    }
    case 'classic_turn_changed':
      return {
        ...s,
        state: 'classic_listening',
        current_turn_player_id: msg.current_turn_player_id,
        current_preview_url: msg.preview_url,
        snippet_duration_s: msg.snippet_duration_s,
        placing_deadline_ms: null,
        last_placement_result: null,
      }
    case 'placement_result': {
      const hands = { ...s.hands }
      if (msg.correct) hands[msg.placer_id] = msg.placer_new_hand
      if (msg.stolen_by && msg.stealer_new_hand)
        hands[msg.stolen_by] = msg.stealer_new_hand
      return {
        ...s,
        state: 'classic_reveal',
        last_placement_result: msg,
        cumulative_scores: msg.card_counts,
        finished_players: msg.finished_players,
        hands,
        current_preview_url: null,
        placing_deadline_ms: null,
        steal_deadline_ms: null,
        steal_placer_id: null,
      }
    }
    case 'game_mode_changed':
      return { ...s, game_mode: msg.mode }
    case 'bingo_settings_changed':
      return {
        ...s,
        bingo_categories: msg.categories,
        bingo_answer_seconds: msg.answer_seconds,
      }
    case 'bingo_game_started':
      return {
        ...s,
        turn_order: msg.participants,
        bingo_cards: msg.cards,
        bingo_categories: msg.categories,
        bingo_marks: Object.fromEntries(msg.participants.map((p) => [p, []])),
        cumulative_scores: Object.fromEntries(
          msg.participants.map((p) => [p, 0]),
        ),
        bingo_round: 0,
        bingo_winners: [],
        last_bingo_result: null,
      }
    case 'bingo_spin':
      return {
        ...s,
        state: 'bingo_spin',
        bingo_round: msg.round,
        bingo_category_index: msg.category_index,
        bingo_prev_title: msg.prev_title,
        bingo_prev_year: msg.prev_year,
        bingo_deadline_ms: null,
        bingo_answered: [],
        bingo_mark_pending: [],
        bingo_erase_pending: [],
        last_bingo_result: null,
        current_preview_url: null,
      }
    case 'bingo_answering':
      return {
        ...s,
        state: 'bingo_answering',
        bingo_deadline_ms: msg.deadline_ms,
        current_preview_url: msg.preview_url,
      }
    case 'bingo_answered':
      return { ...s, bingo_answered: msg.answered }
    case 'bingo_round_result':
      return {
        ...s,
        state: 'bingo_reveal',
        last_bingo_result: msg,
        bingo_deadline_ms: msg.mark_deadline_ms,
        bingo_mark_pending: msg.mark_pending,
        bingo_erase_pending: msg.erase_pending,
        current_preview_url: null,
      }
    case 'bingo_marks_changed': {
      const marks =
        msg.player_id !== null && msg.marks !== null
          ? { ...s.bingo_marks, [msg.player_id]: msg.marks }
          : s.bingo_marks
      return {
        ...s,
        bingo_marks: marks,
        cumulative_scores: msg.card_counts,
        bingo_mark_pending: msg.mark_pending,
        bingo_erase_pending: msg.erase_pending,
      }
    }
    case 'bingo_round_done':
      return {
        ...s,
        bingo_marks: msg.marks,
        cumulative_scores: msg.card_counts,
        bingo_winners: msg.winners,
        bingo_mark_pending: [],
        bingo_erase_pending: [],
        bingo_deadline_ms: null,
      }
    case 'game_over':
      return {
        ...s,
        state: 'game_over',
        cumulative_scores: msg.cumulative_scores,
        finished_players: msg.finished_players,
      }
    case 'rematch_started':
      return {
        ...s,
        state: 'lobby',
        cumulative_scores: Object.fromEntries(s.players.map((p) => [p.id, 0])),
        current_preview_url: null,
        placing_deadline_ms: null,
        steal_deadline_ms: null,
        steal_placer_id: null,
        steal_attempted: [],
        bingo_cards: {},
        bingo_marks: {},
        bingo_round: 0,
        bingo_category_index: null,
        bingo_deadline_ms: null,
        bingo_answered: [],
        bingo_mark_pending: [],
        bingo_erase_pending: [],
        last_bingo_result: null,
        bingo_winners: [],
      }
    case 'promo_state':
      return { ...s, promo_active: msg.active, promo_by: msg.triggered_by }
    case 'cards_adjusted':
      return {
        ...s,
        hands: { ...s.hands, [msg.player_id]: msg.hand },
        cumulative_scores: msg.card_counts,
      }
    // a kicked player is also removed via player_left; the kicked client
    // handles its own player_kicked in onmessage, so here it's a no-op
    case 'player_kicked':
    case 'joined':
    case 'error':
      return s
  }
}

