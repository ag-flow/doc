import { useState } from 'react'
import { Check } from 'lucide-react'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Field } from '../components/ui/field'
import { Tag } from '../components/ui/tag'

/**
 * Page de démonstration interne du système Broadsheet : elle rend TOUS les
 * variants et leurs états. Sert de référence de recette pour chaque écran
 * repris — si un variant n'apparaît pas ici, il n'existe pas dans le système.
 * Non listée dans la navigation (route directe `/design-system`).
 */

const RAMPS: { name: string; prefix: string }[] = [
  { name: 'Neutre', prefix: 'neutral' },
  { name: 'Cyan — accent', prefix: 'accent' },
  { name: 'Magenta — accent 2', prefix: 'accent-2' },
]
const STEPS = [100, 200, 300, 400, 500, 600, 700, 800, 900]

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-8">
      <h6 className="text-accent">{title}</h6>
      <hr className="hr" />
      {children}
    </section>
  )
}

export function DesignSystemPage() {
  const [dialogOpen, setDialogOpen] = useState(false)
  const [seg, setSeg] = useState('arbre')
  const [radio, setRadio] = useState('un')

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <h1>Broadsheet</h1>
      <p className="text-muted">
        Système de design de docflow : composition éditoriale, cyan comme unique
        couleur interactive, magenta réservé à l'échec.
      </p>

      <Section title="Rôles et rampes">
        <div className="mb-3 flex flex-wrap gap-3">
          {[
            ['Papier', 'bg-paper'],
            ['Surface', 'bg-surface'],
            ['Encre', 'bg-ink'],
            ['Accent', 'bg-accent'],
            ['Accent 2', 'bg-accent-2'],
          ].map(([label, cls]) => (
            <div key={label} className="text-center">
              <div className={`${cls} elev-sm h-14 w-24 rounded-md`} />
              <span className="text-muted text-[11px]">{label}</span>
            </div>
          ))}
        </div>
        {RAMPS.map((r) => (
          <div key={r.prefix} className="mb-2">
            <span className="text-muted text-[11px]">{r.name}</span>
            <div className="flex">
              {STEPS.map((s) => (
                /* Variable CSS et non classe Tailwind : une classe construite
                   dynamiquement échapperait à l'extraction statique. */
                <div
                  key={s}
                  className="h-8 flex-1"
                  style={{ background: `var(--color-${r.prefix}-${s})` }}
                  title={`${r.prefix}-${s}`}
                />
              ))}
            </div>
          </div>
        ))}
      </Section>

      <Section title="Typographie">
        <h1>Titre de rang 1 — 42px</h1>
        <h2>Titre de rang 2 — 32px</h2>
        <h3>Titre de rang 3 — 25px</h3>
        <h4>Titre de rang 4 — 20px</h4>
        <h5>Titre de rang 5 — 16px</h5>
        <h6>Surtitre — 13px, petites capitales</h6>
        <p>
          Texte courant à 15px, interligne 1,55. L'<em>italique</em> est une vraie
          italique dessinée, au poids du texte courant, et le <strong>gras</strong>{' '}
          prend l'axe variable de la fonte. Un <a href="#top">lien</a> porte le cyan.
        </p>
        <p className="text-muted">Texte atténué : 55 % d'encre.</p>
      </Section>

      <Section title="Boutons">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <Button>Primaire</Button>
          <Button variant="secondary">Secondaire</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="danger">Destructif</Button>
          <Button variant="icon" aria-label="Valider"><Check size={16} /></Button>
          <Button size="sm">Petit</Button>
        </div>
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <Button disabled>Primaire désactivé</Button>
          <Button variant="secondary" disabled>Secondaire désactivé</Button>
        </div>
        <div className="max-w-xs">
          <Button block>Pleine largeur</Button>
        </div>
        <p className="text-muted mt-2 text-[11px]">
          Survol, état pressé (un cran plus foncé) et anneau de focus au clavier
          sont portés par les classes — testez au clavier avec Tab.
        </p>
      </Section>

      <Section title="Champs">
        <div className="grid max-w-xl gap-3">
          <Field label="Libellé" htmlFor="ds-a" hint="Texte d'aide sous le champ.">
            <Input id="ds-a" placeholder="Saisie…" />
          </Field>
          <Field label="En erreur" htmlFor="ds-b" error="Ce champ est obligatoire.">
            <Input id="ds-b" aria-invalid="true" defaultValue="valeur refusée" />
          </Field>
          <Field label="Désactivé" htmlFor="ds-c">
            <Input id="ds-c" disabled defaultValue="non modifiable" />
          </Field>
          <Field label="Zone de texte" htmlFor="ds-d">
            <textarea id="ds-d" className="input" placeholder="Plusieurs lignes…" />
          </Field>
          <Field label="Liste" htmlFor="ds-e">
            <select id="ds-e" className="input">
              <option>Première valeur</option>
              <option>Seconde valeur</option>
            </select>
          </Field>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-6">
          <div className="seg">
            {['arbre', 'liste'].map((v) => (
              <label key={v} className="seg-opt">
                <input type="radio" name="ds-seg" checked={seg === v} onChange={() => setSeg(v)} />
                {v}
              </label>
            ))}
          </div>
          <div className="flex gap-4">
            {['un', 'deux'].map((v) => (
              <label key={v} className="radio">
                <input type="radio" name="ds-radio" checked={radio === v} onChange={() => setRadio(v)} />
                <span className="dot" />
                Option {v}
              </label>
            ))}
          </div>
        </div>
      </Section>

      <Section title="Tags">
        <div className="flex flex-wrap gap-2">
          <Tag variant="accent">accent</Tag>
          <Tag variant="accent-2">échec</Tag>
          <Tag variant="neutral">neutre</Tag>
          <Tag variant="outline">contour</Tag>
        </div>
      </Section>

      <Section title="Cartes et élévation">
        <div className="grid gap-3 sm:grid-cols-3">
          {(['elev-sm', 'elev-md', 'elev-lg'] as const).map((e) => (
            <article key={e} className={`card ${e}`}>
              <span className="card-kicker">workspace</span>
              <h5 className="card-title">Titre de carte</h5>
              <p className="card-body">
                Réservée aux items discrets d'un listing — jamais à la mise en page.
              </p>
              <div className="card-meta">
                <Tag variant="accent">{e}</Tag>
                <span>modifié hier</span>
              </div>
            </article>
          ))}
        </div>
      </Section>

      <Section title="Table">
        <table className="table">
          <thead>
            <tr><th>Document</th><th>Type</th><th>Statut</th></tr>
          </thead>
          <tbody>
            {[
              ['Cadrage produit', 'epic', 'En cours'],
              ['Socle CSS', 'feature', 'Prêt pour dev'],
              ['Import CSV', 'feature', 'En review'],
            ].map(([a, b, c]) => (
              <tr key={a}>
                <td>{a}</td>
                <td className="text-muted">{b}</td>
                <td><Tag variant="accent">{c}</Tag></td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      <Section title="Dialogue">
        <Button variant="secondary" onClick={() => setDialogOpen(true)}>Ouvrir le dialogue</Button>
        {dialogOpen && (
          <div className="dialog-backdrop" onClick={() => setDialogOpen(false)}>
            <div className="dialog" onClick={(e) => e.stopPropagation()}>
              <h4 className="dialog-title">Supprimer le workspace ?</h4>
              <p className="dialog-body">
                Cette action est irréversible et détruira tout le contenu.
              </p>
              <div className="dialog-actions">
                <Button variant="secondary" onClick={() => setDialogOpen(false)}>Annuler</Button>
                <Button variant="danger" onClick={() => setDialogOpen(false)}>Supprimer</Button>
              </div>
            </div>
          </div>
        )}
      </Section>

      <Section title="Espacement — densité 1.25×">
        <div className="flex items-end gap-3">
          {[1, 2, 3, 4, 6, 8].map((n) => (
            <div key={n} className="text-center">
              <div className="bg-accent-300" style={{ width: n * 5, height: n * 5 }} />
              <span className="text-muted text-[11px]">{n * 5}px</span>
            </div>
          ))}
        </div>
      </Section>
    </div>
  )
}
