import { useState } from 'react'
import { api, type SignatureStatus } from '../api'
import { opt, useEditor, type ToolGroup } from '../editor'
import { ActionButton, OptInput, PagesOption, Section, targetPages } from '../components/ui'

const PERMS: [string, string][] = [
  ['print', 'Printing'], ['copy_content', 'Copying text and images'], ['modify', 'Changing the document'],
  ['annotate', 'Commenting'], ['fill_forms', 'Filling form fields'], ['assemble', 'Page assembly'],
]

export const protectGroup: ToolGroup = {
  id: 'protect',
  label: 'Protect',
  icon: '🔒',
  description: 'Passwords, permissions and removing hidden information',
  needsDoc: true,
  tools: [],
  Panel() {
    const ed = useEditor()
    const info = ed.info!
    return (
      <>
        <Section title="Status">
          <p>{info.encrypted ? '🔒 This document is encrypted (AES).' : '🔓 This document is not encrypted.'}</p>
          {info.encrypted && (
            <>
              <ActionButton label="Enter permissions password…" onClick={async () => {
                const v = await ed.prompt('Permissions password', [{ name: 'pw', label: 'Password', type: 'password' }])
                if (!v?.pw) return
                try {
                  ed.setInfo(await api.unlock(info.id, v.pw))
                  ed.notify('Password accepted', 'success')
                } catch (e) {
                  ed.notify((e as Error).message, 'error')
                }
              }} />
              <ActionButton label="Remove security" kind="danger" onClick={() => ed.runOp('remove_security', {})} />
            </>
          )}
        </Section>
        <Section title="Encrypt with password (AES-256)">
          <OptInput k="enc.user" label="Password to open (optional)" type="password" def="" />
          <OptInput k="enc.owner" label="Permissions password" type="password" def="" />
          <p className="muted small">Allow, without the permissions password:</p>
          {PERMS.map(([k, label]) => <OptInput key={k} k={`enc.perm.${k}`} label={label} type="checkbox" def={true} />)}
          <ActionButton label="Encrypt" kind="primary" onClick={async () => {
            const user_password = opt(ed, 'enc.user', ''), owner_password = opt(ed, 'enc.owner', '')
            if (!user_password && !owner_password) return ed.notify('Enter at least one password', 'error')
            const permissions = Object.fromEntries(PERMS.map(([k]) => [k, opt(ed, `enc.perm.${k}`, true)]))
            const r = await ed.runOp('encrypt', { user_password, owner_password, permissions })
            if (r !== null) ed.notify('Encrypted. Save or download to keep the protected file.', 'success')
          }} />
        </Section>
        <Section title="Remove hidden information">
          <OptInput k="san.metadata" label="Metadata" type="checkbox" def={true} />
          <OptInput k="san.js" label="JavaScript" type="checkbox" def={true} />
          <OptInput k="san.att" label="Attached files" type="checkbox" def={true} />
          <OptInput k="san.hidden" label="Hidden text" type="checkbox" def={true} />
          <OptInput k="san.links" label="Links" type="checkbox" def={false} />
          <OptInput k="san.fields" label="Reset form fields" type="checkbox" def={false} />
          <ActionButton label="Sanitize document" kind="primary" onClick={() => ed.runOp('sanitize', {
            metadata: opt(ed, 'san.metadata', true), javascript: opt(ed, 'san.js', true), attachments: opt(ed, 'san.att', true),
            hidden_text: opt(ed, 'san.hidden', true), links: opt(ed, 'san.links', false), reset_fields: opt(ed, 'san.fields', false),
          })} />
        </Section>
      </>
    )
  },
}

const PATTERNS: [string, string][] = [
  ['email', 'Email addresses'], ['phone', 'Phone numbers'], ['ssn', 'US Social Security numbers'],
  ['credit_card', 'Credit card numbers'], ['date', 'Dates'], ['iban', 'IBAN bank accounts'],
  ['ip_address', 'IP addresses'], ['url', 'Web addresses'],
]

export const redactGroup: ToolGroup = {
  id: 'redact',
  label: 'Redact',
  icon: '⬛',
  description: 'Permanently remove sensitive text, images and hidden data',
  needsDoc: true,
  tools: [
    {
      id: 'redact-text', label: 'Mark text', gesture: 'text', hint: 'Select text to mark it for redaction',
      async onGesture(g, ed) {
        if (g.kind !== 'text') return
        await ed.runOp('mark_redactions', { page: g.page, rects: g.rects, overlay_text: opt(ed, 'red.overlay', ''), from_text: true })
      },
    },
    {
      id: 'redact-area', label: 'Mark area', gesture: 'drag', hint: 'Drag over any area (text, images, drawings)',
      async onGesture(g, ed) {
        if (g.kind !== 'drag') return
        await ed.runOp('mark_redactions', { page: g.page, rects: [g.rect], overlay_text: opt(ed, 'red.overlay', '') })
      },
    },
  ],
  Panel() {
    const ed = useEditor()
    const marked = ed.info?.annotations.filter((a) => a.type === 'Redact').length ?? 0
    return (
      <>
        <Section title="Find text & patterns">
          <OptInput k="red.terms" label="Words or phrases (one per line)" type="textarea" def="" />
          {PATTERNS.map(([k, label]) => <OptInput key={k} k={`red.p.${k}`} label={label} type="checkbox" def={false} />)}
          <OptInput k="red.regex" label="Custom regular expression" def="" />
          <PagesOption k="red" />
          <ActionButton label="Find and mark" kind="primary" onClick={async () => {
            const terms = opt(ed, 'red.terms', '').split('\n').map((s) => s.trim()).filter(Boolean)
            const patterns = PATTERNS.map(([k]) => k).filter((k) => opt(ed, `red.p.${k}`, false))
            const regex = opt(ed, 'red.regex', '') ? [opt(ed, 'red.regex', '')] : []
            const r = await ed.runOp<{ marked: number; matches: string[] }>('search_redact', {
              terms, patterns, regex, pages: targetPages(ed, 'red'), overlay_text: opt(ed, 'red.overlay', ''),
            })
            if (r) ed.notify(`Marked ${r.marked} area(s). Review them, then Apply.`, 'success')
          }} />
        </Section>
        <Section title={`Apply (${marked} marked)`}>
          <OptInput k="red.overlay" label="Overlay text (optional)" def="" placeholder="REDACTED" />
          <ActionButton label="Apply redactions permanently" kind="danger" disabled={!marked} onClick={async () => {
            if (!confirm(`Permanently remove the content under ${marked} marked area(s)? (You can still undo before saving.)`)) return
            await ed.runOp('apply_redactions', {})
          }} />
          <p className="muted small">Redacted text is deleted from the file, not just covered. Also consider Protect → Remove hidden information.</p>
        </Section>
      </>
    )
  },
}

function SignatureList() {
  const ed = useEditor()
  const [sigs, setSigs] = useState<SignatureStatus[] | null>(null)
  return (
    <Section title="Validate signatures">
      <ActionButton label="Validate all signatures" onClick={async () => {
        const r = await ed.withBusy('Validating', () => api.signatures(ed.info!.id))
        if (r) setSigs(r)
      }} />
      {sigs?.length === 0 && <p className="muted">No digital signatures.</p>}
      {sigs?.map((s) => (
        <div key={s.field} className="card">
          <strong>{s.signer ?? 'Unknown signer'}</strong>
          <div className="small">{s.signed_at ? new Date(s.signed_at).toLocaleString() : ''}</div>
          <div className="small">{s.intact ? '✅ Document unchanged since signing' : '❌ Modified after signing'}</div>
          <div className="small">{s.trusted ? '✅ Trusted certificate' : '⚠️ Certificate not in a trusted list (self-signed)'}</div>
          {!s.covers_whole_document && <div className="small">ℹ️ Later revisions were added after this signature</div>}
        </div>
      ))}
    </Section>
  )
}

export const certificatesGroup: ToolGroup = {
  id: 'certificates',
  label: 'Certificates',
  icon: '🎖️',
  description: 'Sign with a digital ID and validate signatures',
  needsDoc: true,
  tools: [
    {
      id: 'cert-sign', label: 'Digitally sign', gesture: 'drag', hint: 'Choose your digital ID in the panel, then drag the signature box',
      async onGesture(g, ed) {
        if (g.kind !== 'drag') return
        const blob_id = opt(ed, 'cert.blob', '')
        if (!blob_id) return ed.notify('Choose or create a digital ID first', 'error')
        const v = await ed.prompt('Sign with certificate', [
          { name: 'passphrase', label: 'Digital ID password', type: 'password' },
          { name: 'reason', label: 'Reason', value: 'I approve this document' },
          { name: 'location', label: 'Location' },
        ], 'Sign')
        if (!v) return
        const r = await ed.runOp('sign_certificate', { blob_id, passphrase: v.passphrase, page: g.page, rect: g.rect, reason: v.reason, location: v.location })
        if (r) ed.notify('Signed. Further edits will show as changes after signing.', 'success')
      },
    },
  ],
  Panel() {
    const ed = useEditor()
    return (
      <>
        <Section title="Digital ID">
          <p className="muted small">{opt(ed, 'cert.name', '') ? `Using ${opt(ed, 'cert.name', '')}` : 'No digital ID selected.'}</p>
          <ActionButton label="Use a .p12 / .pfx file…" onClick={async () => {
            const [file] = await ed.pickFile('.p12,.pfx,application/x-pkcs12')
            if (!file) return
            ed.setOpt('cert.blob', await api.blob(file))
            ed.setOpt('cert.name', file.name)
            ed.setTool('cert-sign')
          }} />
          <ActionButton label="Create self-signed digital ID…" onClick={async () => {
            const v = await ed.prompt('New digital ID', [
              { name: 'name', label: 'Name' }, { name: 'email', label: 'Email' },
              { name: 'organization', label: 'Organization' }, { name: 'passphrase', label: 'Password', type: 'password' },
            ], 'Create')
            if (!v?.name || !v.passphrase) return
            const blob = await ed.withBusy('Creating digital ID', () => api.digitalId(v))
            if (!blob) return
            ed.setOpt('cert.blob', blob)
            ed.setOpt('cert.name', `${v.name}.p12`)
            ed.setTool('cert-sign')
            ed.notify('Digital ID created and downloaded; keep the .p12 file safe.', 'success')
          }} />
        </Section>
        <SignatureList />
      </>
    )
  },
}
