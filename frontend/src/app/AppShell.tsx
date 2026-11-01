import { LogOut, Menu, Moon, Pin, PinOff, Sun, X } from 'lucide-react'
import { useEffect, useRef, useState, type MouseEvent } from 'react'
import { Link, NavLink, Outlet, useLocation, useMatches, useNavigate } from 'react-router'

import { Logo } from '@/components/ui/Logo'
import { Glider } from '@/components/ui/Glider'
import { useAuth } from '@/features/auth/AuthProvider'
import { MentorLauncher, MentorPanel } from '@/features/mentor/MentorPanel'
import { useSystemStatus } from '@/features/system/useSystemStatus'
import { getTheme, setTheme, type Theme } from '@/lib/theme'

import { STUDY_NAV, WORKSHOP_NAV } from './nav'

// Небольшие задержки: меню не дёргается, когда курсор просто пересекает край экрана
const OPEN_DELAY = 120
const CLOSE_DELAY = 250

function readPinned() {
  try {
    return localStorage.getItem('rz.nav.pinned') === '1'
  } catch {
    return false
  }
}

export function AppShell() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const [pinned, setPinned] = useState(readPinned)
  const [hover, setHover] = useState(false)
  const [focusInside, setFocusInside] = useState(false)
  const [drawer, setDrawer] = useState(false)
  const [theme, setThemeState] = useState<Theme>(getTheme)
  const timer = useRef<number | undefined>(undefined)
  // Последний ввод был мышью/пальцем — тогда фокус на пункте меню не держит его открытым
  const pointer = useRef(false)
  // Идёт смена темы: слой View Transition перекрывает страницу, и меню ложно получает «курсор ушёл»
  const switching = useRef(false)
  const aside = useRef<HTMLElement>(null)
  const fullBleed = useMatches().some((m) => (m.handle as { fullBleed?: boolean } | undefined)?.fullBleed)

  const isAdmin = user?.role === 'admin'
  // Пользователь, открывший /workshop по ссылке, видит своё меню и экран 403, а не разделы Мастерской.
  const inWorkshop = isAdmin && pathname.startsWith('/workshop')
  const nav = inWorkshop ? WORKSHOP_NAV : STUDY_NAV

  // На компьютере: закреплено, под курсором или в нём фокус с клавиатуры. На телефоне — шторка.
  const expanded = pinned || hover || focusInside || drawer

  // При переходе закрывается только шторка на телефоне. На компьютере меню остаётся открытым, пока курсор
  // над ним: закроет его уход курсора (onMouseLeave), а не клик по пункту
  useEffect(() => {
    setDrawer(false)
    setFocusInside(false)
  }, [pathname])
  useEffect(() => {
    if (!drawer) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setDrawer(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [drawer])
  useEffect(() => () => window.clearTimeout(timer.current), [])
  useEffect(() => {
    const byPointer = () => (pointer.current = true)
    const byKeyboard = () => (pointer.current = false)
    window.addEventListener('pointerdown', byPointer, true)
    window.addEventListener('keydown', byKeyboard, true)
    return () => {
      window.removeEventListener('pointerdown', byPointer, true)
      window.removeEventListener('keydown', byKeyboard, true)
    }
  }, [])

  const hoverTo = (value: boolean) => {
    if (switching.current) return
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setHover(value), value ? OPEN_DELAY : CLOSE_DELAY)
  }

  const togglePinned = () => {
    setPinned((p) => {
      try {
        localStorage.setItem('rz.nav.pinned', p ? '0' : '1')
      } catch {
        // не запомнится — не страшно
      }
      return !p
    })
  }

  const toggleTheme = (e: MouseEvent<HTMLButtonElement>) => {
    const next = theme === 'dark' ? 'light' : 'dark'
    // Клик с клавиатуры даёт нулевые координаты — тогда круг идёт от центра кнопки
    const box = e.currentTarget.getBoundingClientRect()
    switching.current = true
    setTheme(next, e.clientX || e.clientY ? { x: e.clientX, y: e.clientY } : { x: box.left + box.width / 2, y: box.top + box.height / 2 }).finally(() => {
      switching.current = false
      // За время анимации курсор мог и правда уйти — сверяемся с тем, где он сейчас
      if (!aside.current?.matches(':hover')) hoverTo(false)
    })
    setThemeState(next)
  }

  const onLogout = async () => {
    await logout()
    navigate('/login', { replace: true })
  }

  // Текст справа от иконок не исчезает, а проявляется — меню выезжает плавно, без перескоков
  const fade = `whitespace-nowrap transition-opacity duration-200 ${expanded ? 'opacity-100' : 'opacity-0'}`

  return (
    <div className="min-h-dvh">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[60] focus:rounded-md focus:bg-surface focus:px-4 focus:py-2">
        К содержимому
      </a>

      {/* Телефон и планшет: верхняя панель + шторка */}
      <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-line bg-bg/80 px-4 backdrop-blur lg:hidden">
        <Link to="/" aria-label="Развилка — на главную">
          <Logo />
        </Link>
        <button
          type="button"
          onClick={() => setDrawer(true)}
          className="grid size-10 place-items-center rounded-md text-muted hover:bg-surface-2 hover:text-text"
          aria-label="Открыть меню"
          aria-expanded={drawer}
        >
          <Menu className="size-5" />
        </button>
      </header>
      {drawer && <div className="fixed inset-0 z-40 bg-black/50 lg:hidden" onClick={() => setDrawer(false)} aria-hidden />}

      <aside
        ref={aside}
        onMouseEnter={() => hoverTo(true)}
        onMouseLeave={() => hoverTo(false)}
        // Раскрываем по фокусу только при навигации с клавиатуры: после клика мышью фокус остаётся
        // на ссылке, и меню иначе «залипало» бы открытым. :focus-visible бывает ложноположительным,
        // поэтому дополнительно помним, что последним был указатель
        onFocus={(e) => setFocusInside(!pointer.current && (e.target as HTMLElement).matches(':focus-visible'))}
        onBlur={(e) => !e.currentTarget.contains(e.relatedTarget) && setFocusInside(false)}
        className={`fixed inset-y-0 left-0 z-50 w-[272px] overflow-hidden border-r border-line bg-surface transition-[transform,width,box-shadow] duration-300 ease-[var(--ease)] lg:translate-x-0 ${
          drawer ? 'translate-x-0' : '-translate-x-full'
        } ${expanded ? 'lg:w-[256px]' : 'lg:w-[72px]'} ${expanded && !pinned ? 'lg:shadow-[24px_0_60px_-20px_rgb(0_0_0/0.6)]' : ''}`}
        aria-label="Главное меню"
      >
        <div className="flex h-full w-[256px] flex-col gap-6 px-3 py-4 max-lg:w-full">
          <div className="flex items-center justify-between px-1.5">
            <Link to="/" aria-label="Развилка — на главную">
              <Logo textClassName={fade} />
            </Link>
            <button
              type="button"
              onClick={() => setDrawer(false)}
              className="grid size-9 place-items-center rounded-md text-muted hover:bg-surface-2 hover:text-text lg:hidden"
              aria-label="Закрыть меню"
            >
              <X className="size-5" />
            </button>
          </div>

          {isAdmin && (
            <div className={`relative grid grid-cols-2 rounded-md border border-line bg-surface-2/50 p-1 text-sm ${fade} ${expanded ? '' : 'pointer-events-none'}`} role="group" aria-label="Режим">
              <Glider className={inWorkshop ? '!bg-ai-soft' : '!bg-accent-soft'} />
              {[
                { to: '/', label: 'Учёба', active: !inWorkshop },
                { to: '/workshop', label: 'Мастерская', active: inWorkshop },
              ].map((m) => (
                <Link
                  key={m.to}
                  to={m.to}
                  aria-current={m.active ? 'page' : undefined}
                  className={`relative z-[1] rounded-[6px] px-2 py-1.5 text-center font-medium transition-colors duration-300 ${
                    m.active ? (m.to === '/' ? 'text-accent' : 'text-ai') : 'text-muted hover:text-text'
                  }`}
                >
                  {m.label}
                </Link>
              ))}
            </div>
          )}

          <nav aria-label={inWorkshop ? 'Мастерская' : 'Учёба'} className="relative flex flex-col gap-1">
            <Glider className="shadow-[inset_2px_0_0_var(--accent)]" />
            <p className={`eyebrow px-3 pb-1 ${fade}`} aria-hidden={!expanded}>
              {inWorkshop ? 'Мастерская' : 'Учёба'}
            </p>
            {nav.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                end={to === '/' || to === '/workshop'}
                className={({ isActive }) =>
                  `group relative z-[1] flex h-10 items-center gap-3 rounded-md px-[15px] text-[15px] transition-colors duration-300 ${
                    isActive ? 'text-text' : 'text-muted hover:bg-surface-2/60 hover:text-text'
                  }`
                }
              >
                <Icon className="size-[18px] shrink-0 transition-transform duration-200 group-hover:scale-110" aria-hidden />
                <span className={fade}>{label}</span>
              </NavLink>
            ))}
          </nav>

          <div className="mt-auto flex flex-col gap-1 border-t border-line pt-4">
            <StatusLine fade={fade} />
            <button type="button" onClick={toggleTheme} className={sideButton}>
              {theme === 'dark' ? <Sun key="sun" className="icon-swap size-[18px] shrink-0" aria-hidden /> : <Moon key="moon" className="icon-swap size-[18px] shrink-0" aria-hidden />}
              <span className={fade}>{theme === 'dark' ? 'Светлая тема' : 'Тёмная тема'}</span>
            </button>
            <button type="button" onClick={togglePinned} className={`${sideButton} max-lg:hidden`} aria-pressed={pinned}>
              {pinned ? <PinOff className="size-[18px] shrink-0" aria-hidden /> : <Pin className="size-[18px] shrink-0" aria-hidden />}
              <span className={fade}>{pinned ? 'Открепить меню' : 'Закрепить меню'}</span>
            </button>
            <button type="button" onClick={onLogout} className={sideButton}>
              <LogOut className="size-[18px] shrink-0" aria-hidden />
              <span className={`min-w-0 truncate ${fade}`}>
                Выйти <span className="text-faint">· {user?.display_name}</span>
              </span>
            </button>
          </div>
        </div>
      </aside>

      <div aria-hidden data-mode={inWorkshop ? 'workshop' : 'study'} className={`ambient-light ${pinned ? 'lg:left-[256px]' : 'lg:left-[72px]'}`} />
      <main id="main" className={`relative z-[1] min-w-0 transition-[padding] duration-300 ease-[var(--ease)] ${pinned ? 'lg:pl-[256px]' : 'lg:pl-[72px]'}`}>
        <div className={fullBleed ? 'w-full px-4 py-6 sm:px-6 xl:p-0' : 'mx-auto w-full max-w-[1480px] px-4 py-6 sm:px-6 lg:px-10 lg:py-8'}>
          <Outlet />
        </div>
      </main>
      {/* Наставник — на любом экране; в Мастерской он не нужен: там Claude работает через Генерацию */}
      {!inWorkshop && (
        <>
          <MentorLauncher hiddenOnDesktop={fullBleed} />
          <MentorPanel />
        </>
      )}
    </div>
  )
}

const sideButton =
  'group flex h-10 items-center gap-3 rounded-md px-[15px] text-left text-[15px] text-muted transition-colors hover:bg-surface-2/60 hover:text-text'

function StatusLine({ fade }: { fade: string }) {
  const status = useSystemStatus()
  const down = status === 'down'
  const alive = status && status !== 'down' ? status.workers.filter((w) => w.alive).length : 0
  const total = status && status !== 'down' ? status.workers.length : 5
  const ok = !down && status !== null && alive === total
  const label = status === null ? 'Проверяем сервисы…' : down ? 'API не отвечает' : ok ? 'Все сервисы работают' : `Работают ${alive} из ${total} воркеров`

  return (
    <div className="flex h-9 items-center gap-3 px-[20px] font-mono text-xs text-muted" title={label}>
      <span className={`size-2 shrink-0 rounded-full ${ok ? 'bg-accent shadow-[0_0_10px_var(--accent)]' : status === null ? 'bg-faint' : 'bg-danger'}`} aria-hidden />
      <span role="status" className={fade}>
        {label}
      </span>
    </div>
  )
}
