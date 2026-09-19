/**
 * The documentation, in the reader's language.
 *
 * `content.ts` is the English edition and the canonical one - it fixes the
 * section order and the anchors. Each other language is a sibling module of the
 * same shape. The view asks for one language; anything a translation has not
 * caught up with falls back to English section by section, so adding a section
 * or a language never leaves a hole in the page.
 */
import {
  DOC_GROUPS as EN_GROUPS,
  DOC_SECTIONS as EN_SECTIONS,
  type DocGroup,
  type DocSection,
} from './content'
import { DOC_GROUPS as DE_GROUPS, DOC_SECTIONS as DE_SECTIONS } from './de'
import { DOC_GROUPS as ES_GROUPS, DOC_SECTIONS as ES_SECTIONS } from './es'
import { DOC_GROUPS as FR_GROUPS, DOC_SECTIONS as FR_SECTIONS } from './fr'
import { DOC_GROUPS as RU_GROUPS, DOC_SECTIONS as RU_SECTIONS } from './ru'
import { DOC_GROUPS as ZH_GROUPS, DOC_SECTIONS as ZH_SECTIONS } from './zh'

export type Docs = {
  groups: DocGroup[]
  sections: DocSection[]
}

type Edition = { groups: DocGroup[]; sections: DocSection[] }

const ENGLISH: Edition = { groups: EN_GROUPS, sections: EN_SECTIONS }

const EDITIONS: Record<string, Edition> = {
  en: ENGLISH,
  de: { groups: DE_GROUPS, sections: DE_SECTIONS },
  es: { groups: ES_GROUPS, sections: ES_SECTIONS },
  fr: { groups: FR_GROUPS, sections: FR_SECTIONS },
  ru: { groups: RU_GROUPS, sections: RU_SECTIONS },
  zh: { groups: ZH_GROUPS, sections: ZH_SECTIONS },
}

export function docsFor(locale: string): Docs {
  const edition: Edition = EDITIONS[locale] ?? ENGLISH
  const translated = new Map(edition.sections.map((section) => [section.id, section]))
  return {
    // Rendered in the English order, so the anchors and the rail do not move
    // when the reader switches language mid-page.
    sections: EN_SECTIONS.map((english) => translated.get(english.id) ?? english),
    groups: EN_GROUPS.map((english, index) => ({
      label: edition.groups[index]?.label ?? english.label,
      ids: english.ids,
    })),
  }
}

export type { DocGroup, DocSection }