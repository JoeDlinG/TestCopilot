/**
 * 首次运行导航引导（Issue: 第一次安装运行时，运行一次导航提示）
 *
 * Uses AntD's ``Tour``: it already handles the spotlight mask, keyboard escape
 * and the prev/next chrome, so there is no point hand-rolling an overlay.
 *
 * "Once" is enforced by a localStorage flag written on **both** finish and
 * skip — a user who dismisses it should not be asked again on every launch.
 * The same component is reused by 帮助 ▸ 重新观看导航, which opens it without
 * touching the flag.
 */
import { Tour } from 'antd'
import type { TourProps } from 'antd'

import { useI18n } from '../../i18n'

/** Where the "already seen" bit lives. Bump the suffix to re-run for everyone. */
export const TOUR_STORAGE_KEY = 'testcopilot.onboarding.v1'

export function markTourSeen() {
  try {
    localStorage.setItem(TOUR_STORAGE_KEY, '1')
  } catch {
    /* private mode / storage disabled — the tour simply shows again */
  }
}

export function hasSeenTour(): boolean {
  try {
    return localStorage.getItem(TOUR_STORAGE_KEY) === '1'
  } catch {
    return false
  }
}

/** Resolve a ``data-tour`` anchor; AntD centres the card when it is missing. */
const anchor = (name: string) => (): HTMLElement =>
  (document.querySelector(`[data-tour="${name}"]`) as HTMLElement) ||
  (document.body as HTMLElement)

interface Props {
  open: boolean
  onClose: () => void
}

export default function OnboardingTour({ open, onClose }: Props) {
  const { t } = useI18n()

  const steps: TourProps['steps'] = [
    {
      title: t('tour.welcome'),
      description: t('tour.welcomeBody'),
      target: anchor('logo'),
    },
    {
      title: t('nav.group.config'),
      description: t('tour.step.config'),
      target: anchor('nav'),
      placement: 'right',
    },
    {
      title: t('nav.group.design'),
      description: t('tour.step.design'),
      target: anchor('nav'),
      placement: 'right',
    },
    {
      title: t('nav.group.system'),
      description: t('tour.step.system'),
      target: anchor('nav'),
      placement: 'right',
    },
    {
      title: `${t('top.dashboards')} / ${t('top.tools')}`,
      description: t('tour.step.top'),
      target: anchor('topmenus'),
      placement: 'bottomLeft',
    },
    {
      title: t('tour.step.searchTitle'),
      description: t('tour.step.search'),
      target: anchor('search'),
      placement: 'bottomRight',
    },
    {
      title: t('help.menu'),
      description: t('tour.step.help'),
      target: anchor('help'),
      placement: 'bottomRight',
    },
    {
      title: t('tour.step.dockTitle'),
      description: t('tour.step.dock'),
      target: anchor('dock'),
      placement: 'left',
    },
  ]

  return (
    <Tour
      open={open}
      onClose={onClose}
      steps={steps}
      zIndex={1300}
      indicatorsRender={(current, total) => (
        <span style={{ fontSize: 12, opacity: 0.65 }}>
          {t('tour.progress', { n: (current ?? 0) + 1, total })}
        </span>
      )}
    />
  )
}
