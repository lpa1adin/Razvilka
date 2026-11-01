import {
  Activity,
  LayoutDashboard,
  BookOpen,
  ClipboardCheck,
  FileStack,
  FolderGit2,
  GitFork,
  GraduationCap,
  House,
  Library,
  Scale,
  SquareTerminal,
  Users,
  Wand2,
  type LucideIcon,
} from 'lucide-react'

export type NavItem = {
  to: string
  label: string
  icon: LucideIcon
  /** что будет на экране — показываем на заглушке, пока раздел не готов */
  about: string
  /** этап из docs/BRIEF.md §9, на котором раздел появится; нет — раздел уже работает */
  stage?: string
}

export const STUDY_NAV: NavItem[] = [
  { to: '/', label: 'Главная', icon: House, about: '' },
  { to: '/courses', label: 'Курсы', icon: GraduationCap, about: 'Курсы, модули и уроки: теория, тест, практика и развилка в каждом уроке.' },
  { to: '/library', label: 'Библиотека', icon: Library, about: 'Фрагменты теории из проверенных источников с автором, лицензией и ссылкой на оригинал.' },
  { to: '/practice', label: 'Практика', icon: SquareTerminal, about: 'Песочница с кнопкой «Проверить», тесты без повторов и тренажёр архитектуры.' },
  { to: '/projects', label: 'Мои проекты', icon: FolderGit2, about: 'Пути «напиши заново сам»: проект по этапам, со сдачей каждого этапа на проверку.' },
  { to: '/forks', label: 'Развилки', icon: GitFork, about: 'Журнал ваших решений: вопрос, выбор, обоснование, оценка и как сделали в эталоне.' },
  { to: '/reviews', label: 'Проверки', icon: ClipboardCheck, about: 'Сдачи практикумов с оценкой Оценщика и отчёты Ревьюера.' },
]

export const WORKSHOP_NAV: NavItem[] = [
  { to: '/workshop', label: 'Обзор', icon: LayoutDashboard, about: '' },
  { to: '/workshop/generate', label: 'Генерация', icon: Wand2, about: 'Выбрать проект → утвердить план → проверить черновик → опубликовать курс или задание.' },
  { to: '/workshop/content', label: 'Контент', icon: FileStack, about: 'Курсы, задания, вопросы и развилки: статусы, версии, редактирование.' },
  { to: '/workshop/sources', label: 'Источники', icon: BookOpen, about: 'Белый список источников, импорты сборщика и лицензии.' },
  { to: '/workshop/grading', label: 'Оценивание', icon: Scale, about: 'Правила Ревьюера, рубрика Оценщика, эталоны, практикумы и сдачи.' },
  { to: '/workshop/users', label: 'Пользователи', icon: Users, about: 'Учётки и роли.' },
  { to: '/workshop/system', label: 'Система', icon: Activity, about: '' },
]

export const GRAFANA_URL = import.meta.env.VITE_GRAFANA_URL ?? `${location.protocol}//${location.hostname}:3060`
