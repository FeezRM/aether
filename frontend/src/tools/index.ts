import type { Tool, ToolGroup } from '../editor'
import { commentGroup, stampGroup } from './comment'
import {
  accessibilityGroup, actionsGroup, combineGroup, compareGroup, createGroup, exportGroup, measureGroup,
  ocrGroup, optimizeGroup, organizeGroup,
} from './docs'
import { editGroup, enhanceGroup, propertiesGroup } from './edit'
import { fillSignGroup, formsGroup } from './forms'
import { certificatesGroup, protectGroup, redactGroup } from './protect'

/** Tool groups, named after the Acrobat Pro tools they replace. */
export const GROUPS: ToolGroup[] = [
  editGroup, commentGroup, organizeGroup, combineGroup, createGroup, exportGroup,
  fillSignGroup, formsGroup, protectGroup, redactGroup, ocrGroup, enhanceGroup,
  compareGroup, optimizeGroup, stampGroup, certificatesGroup, measureGroup,
  accessibilityGroup, actionsGroup, propertiesGroup,
]

export const TOOLS: Record<string, Tool> = Object.fromEntries(
  GROUPS.flatMap((g) => g.tools.map((t) => [t.id, t])),
)
