import { useState, type FormEvent } from 'react'
import { Button } from './ui/Button'
import { Card, CardContent, CardHeader } from './ui/Card'

interface LoginPageProps {
  onSubmit: (password: string) => Promise<void>
}

export function LoginPage({ onSubmit }: LoginPageProps) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await onSubmit(password)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not sign in.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md items-center px-6 py-12">
      <Card className="w-full">
        <CardHeader className="border-b border-zinc-100 p-8">
          <p className="text-sm font-medium text-zinc-500">Northstar Facilities B.V.</p>
          <h1 className="pt-2 text-2xl font-semibold tracking-tight text-zinc-950">
            Document review
          </h1>
          <p className="pt-1 text-sm leading-6 text-zinc-600">
            Enter the shared access password to continue.
          </p>
        </CardHeader>
        <CardContent className="p-8">
          <form className="space-y-4" onSubmit={(event) => void handleSubmit(event)}>
            <label className="block">
              <span className="text-sm font-medium text-zinc-900">Password</span>
              <input
                type="password"
                name="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="mt-2 h-10 w-full rounded-lg border border-zinc-200 bg-white px-3 text-sm text-zinc-950 shadow-sm outline-none focus:border-zinc-400 focus:ring-2 focus:ring-zinc-200"
                required
              />
            </label>
            {error && (
              <div
                role="alert"
                className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800"
              >
                {error}
              </div>
            )}
            <Button type="submit" className="w-full" disabled={submitting || !password}>
              {submitting ? 'Signing in…' : 'Sign in'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  )
}
