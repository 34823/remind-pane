export type Item = { id: string; text: string; due: string | null; repeat: string | null; failed: boolean; done: boolean }

declare module 'claude-code' {
  interface PluginState {
    'remind-pane': { items: Item[]; error: string | null; n: number }
  }
}
