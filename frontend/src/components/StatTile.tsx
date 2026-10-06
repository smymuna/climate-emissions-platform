interface Props {
  label: string
  value: string
  note?: string
  delta?: { text: string; good: boolean } | null
}

export function StatTile({ label, value, note, delta }: Props) {
  return (
    <div className="card tile">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {delta && (
        <div className={delta.good ? 'delta-good' : 'delta-bad'}>
          <span aria-hidden="true">{delta.good ? '▼ ' : '▲ '}</span>
          {delta.text}
        </div>
      )}
      {note && <div className="note">{note}</div>}
    </div>
  )
}
