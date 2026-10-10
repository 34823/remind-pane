import { expect, mock, test } from 'claude-code/testing'

const PANE = { component: 'Pane', requestId: 'remind', viewport: { columns: 60, rows: 30 },
  props: { title: 'Reminders', isFocused: true, bodyColumns: 56, placement: 'dock', scroll: { offset: 0, bodyRows: 28 }, view: {} } } as const
const OPTS = { options: { python: '/py', dataDir: '~/rem', timezone: 'Europe/Berlin', telegramChat: '42' } }
const ok = (stdout = '') => ({ value: { exitCode: 0, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }) as any

test('checkbox toggles by id, a new item is added without a date', OPTS, async ($, on) => {
  mock.clock(on)
  const runs: string[][] = []
  const envs: Record<string, string>[] = []
  const items = [
    { id: 'aaa', text: 'buy milk', due: null, repeat: null, failed: false, done: false },
    { id: 'bbb', text: 'call Anna', due: '2026-10-10 18:00 UTC', repeat: null, failed: false, done: true },
  ]
  on('ui.open', async () => ({ value: { isPlaced: true } }) as any)
  on('process.run', async (_: any, e: any) => {
    const argv = [...e.argv].slice(3) as string[]
    runs.push(argv)
    if (e.init?.env) envs.push(e.init.env)
    if (argv[0] === 'done') items.find(i => i.id === argv[1])!.done = true
    if (argv[0] === 'del') items.splice(items.findIndex(i => i.id === argv[1]), 1)
    if (argv[0] === 'undone') items.find(i => i.id === argv[1])!.done = false
    if (argv[0] === 'add') items.push({ id: 'ccc', text: argv[2]!, due: null, repeat: null, failed: false, done: false })
    return ok(argv[0] === 'list' ? JSON.stringify(items) : 'ok')
  })
  await $.command.run({ command: 'remind-pane', args: '', origin: { kind: 'user' } } as any)
  const ui = await $.ui.mount({ plugin: 'remind-pane', surface: 'terminal', ...PANE })

  expect(await ui.find({ type: 'Button', text: /buy milk/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', text: /call Anna/ })).toBeDefined()

  await ui.press({ key: 'i-aaa' })
  expect(runs).toContainEqual(['done', 'aaa'])
  expect(await ui.find({ type: 'Button', text: /buy milk/ })).toBeDefined()

  await ui.press({ key: 'i-bbb' })
  expect(runs).toContainEqual(['undone', 'bbb'])
  expect(await ui.find({ type: 'Button', text: /call Anna/ })).toBeDefined()

  await ui.press({ key: 'x-bbb' })
  expect(runs).toContainEqual(['del', 'bbb'])
  expect(await ui.find({ type: 'Button', text: /call Anna/ })).toBeUndefined()

  await ui.input({ key: 'new-0', text: 'write the README' })
  expect(runs).toContainEqual(['add', '--text', 'write the README'])
  expect(await ui.find({ type: 'Button', text: /write the README/ })).toBeDefined()
  expect(await ui.find({ type: 'Input', key: 'new-1' })).toBeDefined()
  expect(envs.at(-1)).toMatchObject({ REMIND_PANE_TZ: 'Europe/Berlin', REMIND_PANE_DATA: '~/rem', REMIND_PANE_TELEGRAM_CHAT: '42' })
  await ui.unmount()
})

test('a CLI error is shown and the field is kept', OPTS, async ($, on) => {
  mock.clock(on)
  on('ui.open', async () => ({ value: { isPlaced: true } }) as any)
  on('process.run', async (_: any, e: any) => {
    const argv = [...e.argv].slice(3) as string[]
    if (argv[0] === 'add') return { value: { exitCode: 1, stdout: '', stderr: 'text is empty or longer than 1000 characters', isStdoutTruncated: false, isStderrTruncated: false } } as any
    return ok('[]')
  })
  await $.command.run({ command: 'remind-pane', args: '', origin: { kind: 'user' } } as any)
  const ui = await $.ui.mount({ plugin: 'remind-pane', surface: 'terminal', ...PANE })
  await ui.input({ key: 'new-0', text: 'x' })
  expect(await ui.find({ type: 'Text', text: /text is empty/ })).toBeDefined()
  expect(await ui.find({ type: 'Input', key: 'new-0' })).toBeDefined()
  await ui.unmount()
})
