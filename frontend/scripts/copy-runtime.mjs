// Копирует Pyodide (Python в браузере) в public/, чтобы платформа работала без интернета и без CDN.
import { copyFileSync, mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const from = join(root, 'node_modules', 'pyodide')
const to = join(root, 'public', 'pyodide')
mkdirSync(to, { recursive: true })
for (const file of ['pyodide.mjs', 'pyodide.asm.mjs', 'pyodide.asm.wasm', 'python_stdlib.zip', 'pyodide-lock.json']) {
  copyFileSync(join(from, file), join(to, file))
}
console.log('Pyodide скопирован в public/pyodide')
