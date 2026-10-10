import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Item } from '../types'

// Reminders in a right-hand pane: a list, a done checkbox, a line for a new one. Data and edits go only through the
// bundled CLI backend/remind.py (it locks the file and drops yesterday's done items); numbers are not used — only ids.

type Options = { python?: string; dataDir?: string; timezone?: string; telegramToken?: string; telegramChat?: string }

const PANE = 'remind'
const REFRESH_MS = 30_000
const ACCENT = '#7dcfff'
const GREEN = '#9ece6a'
const RED = '#f7768e'
const HOVER = '#3a444b'

const items = atom({ plugin: 'remind-pane', key: 'items' } as const, [])
const error = atom({ plugin: 'remind-pane', key: 'error' } as const, null)
const n = atom({ plugin: 'remind-pane', key: 'n' } as const, 0) // key of the input field: changing it clears the field

// Set by register (a change of options reloads the module): the options and the CLI's environment.
let opt: Options = {}
const env: Record<string, string> = {}

async function setup() {
  if (opt.dataDir) env.REMIND_PANE_DATA = opt.dataDir // the CLI expands a leading ~ itself
  if (opt.timezone) env.REMIND_PANE_TZ = opt.timezone
  if (opt.telegramToken) env.REMIND_PANE_TELEGRAM_TOKEN = opt.telegramToken
  if (opt.telegramChat) env.REMIND_PANE_TELEGRAM_CHAT = opt.telegramChat
}

async function cli($: EngineInterface, args: string[]) {
  setup()
  const r = await $.process.run([opt.python || 'python3', '-I', `${$.plugin.root}/backend/remind.py`, ...args], { env, timeoutMs: 30_000 })
  if (r.exitCode !== 0) throw new Error((r.stderr || r.stdout).trim().split('\n').pop() || `exit code ${r.exitCode}`)
  return r.stdout
}

async function refresh($: EngineInterface) {
  try {
    const list: Item[] = JSON.parse(await cli($, ['list', '--json']) || '[]')
    await update($, items, () => list)
    await update($, error, () => null) // a successful refresh clears the old error, otherwise it would stay forever
  } catch (e) {
    await update($, error, () => String((e as Error).message ?? e))
  }
}

async function act($: EngineInterface, args: string[]) {
  await update($, error, () => null)
  let failure: string | null = null
  try {
    await cli($, args)
  } catch (e) {
    failure = String((e as Error).message ?? e)
  }
  await refresh($) // refresh clears the error, so the action's error is set after it
  if (failure) await update($, error, () => failure)
  return !failure
}

let isRegistered = false

async function ensureCommand($: EngineInterface) {
  if (isRegistered) return
  isRegistered = true
  await $.command.register({ name: 'remind-pane', description: 'Reminders in a pane: checkboxes and an add field' })
}

let timer: { cancel: () => void } | undefined
let isOpen = false // polling only after /remind-pane: the plugin is loaded in every session
let wasOpen = false // the pane was open at /clear — reopen it afterwards

async function afterClear($: EngineInterface) {
  if (!wasOpen) return
  wasOpen = false
  isOpen = true
  timer?.cancel()
  timer = $.clock.every(REFRESH_MS, () => void refresh($))
  await refresh($)
  if (!(await $.ui.panes()).some(p => p.id === PANE)) await $.ui.open({ id: PANE, title: 'Reminders' })
}

export const register: Register = (on, options) => {
  opt = options as Options

  // session.start does not arrive if the plugin was attached mid-session (/reload-plugins) — also register on the first prompt
  on('session.start', async ($, e, next) => {
    await ensureCommand($)

    return next(e)
  })

  on('prompt.submit', async ($, e, next) => {
    await ensureCommand($)

    return next(e)
  })

  on('command.run', { command: 'remind-pane' }, async $ => {
    isOpen = true
    timer?.cancel()
    timer = $.clock.every(REFRESH_MS, () => void refresh($))
    await refresh($)
    await $.ui.open({ id: PANE, title: 'Reminders', focus: true })

    return { text: 'Reminders pane opened.' }
  })

  on('session.end', async ($, e, next) => {
    if (e.reason === 'clear' && isOpen) {
      wasOpen = true
      $.clock.after(1_000, () => void afterClear($)) // in case classic.SessionStart below does not arrive
    }
    return next(e)
  })
  on('classic.SessionStart', async ($, e, next) => {
    if (e.source === 'clear') await afterClear($)
    return next(e)
  })

  on('ui.close', async ($, e, next) => {
    if (e.id === PANE) isOpen = false
    return next(e)
  }).catch(($, e, next) => next(e))

  on('turn.complete', async ($, e, next) => {
    if (isOpen) void refresh($)

    return next(e)
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Button } = $.ui.resolve(e)
    const el = $.ui.resolve(e) as any
    const Input = 'Input' in el ? el.Input : undefined
    const list = await read($, items)
    const err = await read($, error)
    const k = await read($, n)
    const open = list.filter(i => !i.done).length

    const done = list.length - open
    const BAR = 16
    const filled = list.length ? Math.round((done / list.length) * BAR) : 0

    return (
      <Box flexDirection="column" paddingX={1} width="100%">
        <Box justifyContent="space-between">
          <Text bold color={ACCENT}>Reminders</Text>
          <Text dimColor>{list.length === 0 ? 'empty' : `${open} left`}</Text>
        </Box>
        {list.length > 0 && (
          <Text>
            <Text color={GREEN}>{'█'.repeat(filled)}</Text>
            <Text dimColor>{'░'.repeat(BAR - filled)}</Text>
            <Text dimColor>{`  ${done}/${list.length}`}</Text>
        </Text>
        )}
        <Box marginTop={2} flexDirection="column">
        {err && <Text color="red">{err}</Text>}
        {Input && (
          <Input
            key={`new-${k}`}
            label="+"
            placeholder="new reminder, Enter"
            submitLabel="add"
            onSubmit={(value: string) => {
              const text = value.trim()
              if (!text) return
              void act($, ['add', '--text', text]).then(isOk => isOk && update($, n, v => v + 1))
            }}
          />
        )}
        </Box>
        <Box>
        <Text dimColor wrap="truncate">{'─'.repeat(200)}</Text>
        </Box>
        {list.map(i => (
          <Box
            key={`r-${i.id}`}
            flexDirection="row"
            gap={1}
            hover={{ backgroundColor: HOVER }}
          >
            <Button plain key={`m-${i.id}`} onPress={() => void act($, [i.done ? 'undone' : 'done', i.id])}>
              <Text color={i.done ? GREEN : ACCENT} bold>{i.done ? '[✔]' : '[ ]'}</Text>
            </Button>
            <Box flexDirection="column" flexGrow={1} flexShrink={1}>
              <Button
                plain
                key={`i-${i.id}`}
                dimColor={i.done}
                onPress={() => void act($, [i.done ? 'undone' : 'done', i.id])}
              >
                <Text strikethrough={i.done}>{i.text}</Text>
              </Button>
              {(i.due || i.repeat || i.failed) && (
                <Text dimColor>
                  {i.due ?? ''}
                  {i.repeat ? ` ↻ ${i.repeat}` : ''}
                  {i.failed ? <Text color={RED}>  NOT DELIVERED</Text> : null}
                </Text>
              )}
            </Box>
            <Button plain key={`x-${i.id}`} dimColor hover={{ color: RED }} onPress={() => void act($, ['del', i.id])}>
              ✕
            </Button>
          </Box>
        ))}
      </Box>
    )
  })
}
