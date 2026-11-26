import { useEffect, useRef } from 'react'

export default function ConfirmModal({ title, body, confirmLabel = 'Confirm', onConfirm, onCancel, children }) {
  const confirmRef = useRef(null)

  useEffect(() => {
    confirmRef.current?.focus()
    const onKey = (e) => e.key === 'Escape' && onCancel()
    addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [onCancel])

  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title" onClick={(e) => e.stopPropagation()}>
        <span className="modal-mark" aria-hidden="true" />
        <h2 id="modal-title">{title}</h2>
        {body && <p className="muted">{body}</p>}
        {children}
        <p className="modal-question">Are you sure you want to enter?</p>
        <div className="modal-actions">
          <button className="btn ghost" onClick={onCancel}>Not now</button>
          <button className="btn" ref={confirmRef} onClick={onConfirm}>{confirmLabel}</button>
        </div>
      </div>
    </div>
  )
}
