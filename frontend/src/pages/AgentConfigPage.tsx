import { useState, useCallback } from 'react'
import { Activity, Mic, Settings, Shield } from 'lucide-react'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Separator } from '@/components/ui/separator'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useHealthStatus } from '@/hooks/use-config'

/** Default system prompt for Maya, shown in the editor. */
const DEFAULT_SYSTEM_PROMPT = `You are Maya, a warm and professional virtual receptionist at Sunrise Health Clinic.

Your responsibilities:
- Greet patients warmly and by name when recognized
- Book, reschedule, and cancel appointments
- Answer questions about insurance, services, hours, and policies using the clinic knowledge base
- Use SHORT sentences (1-2 sentences max per turn) appropriate for voice conversation
- Always confirm before taking actions ("I have Thursday at 2:30 with Dr. Patel -- shall I book that?")
- Escalate when: patient mentions chest pain/emergency, is very frustrated, asks for a human, or the topic is a billing dispute
- Never give medical advice
- Use natural filler acknowledgments ("Got it", "Sure thing", "Of course")

Tone: Professional, empathetic, concise. You are a healthcare receptionist, not a chatbot.`

/** Mapping of service name to a user-friendly display label. */
function serviceLabel(key: string): string {
  const labels: Record<string, string> = {
    api: 'FastAPI Backend',
    ollama: 'Ollama LLM',
    voice_agent: 'Voice Agent',
    database: 'SQLite Database',
    chromadb: 'ChromaDB (RAG)',
    stt: 'Speech-to-Text',
    tts: 'Text-to-Speech',
  }
  return labels[key] ?? key
}

/** Return a colored badge for a service status string. */
function StatusBadge({ status }: { status: string }) {
  const normalized = status.toLowerCase()
  if (normalized === 'ok' || normalized === 'healthy' || normalized === 'running') {
    return (
      <Badge className="bg-emerald-500/15 text-emerald-700 border-emerald-500/25 dark:text-emerald-400">
        {status}
      </Badge>
    )
  }
  if (normalized === 'degraded' || normalized === 'slow') {
    return (
      <Badge className="bg-amber-500/15 text-amber-700 border-amber-500/25 dark:text-amber-400">
        {status}
      </Badge>
    )
  }
  return (
    <Badge className="bg-red-500/15 text-red-700 border-red-500/25 dark:text-red-400">
      {status}
    </Badge>
  )
}

export default function AgentConfigPage() {
  const { data: health, isLoading: healthLoading, error: healthError } = useHealthStatus()
  const [systemPrompt, setSystemPrompt] = useState(DEFAULT_SYSTEM_PROMPT)
  const [saveMessage, setSaveMessage] = useState<string | null>(null)

  const handleSavePrompt = useCallback(() => {
    setSaveMessage('System prompt saved locally. Config API coming soon.')
    setTimeout(() => setSaveMessage(null), 3000)
  }, [])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Agent Configuration</h1>
        <p className="text-muted-foreground mt-1">
          Monitor system health, edit the agent prompt, and view settings.
        </p>
      </div>

      <Tabs defaultValue="health" className="w-full">
        <TabsList className="grid w-full grid-cols-3 max-w-md">
          <TabsTrigger value="health" className="flex items-center gap-1.5">
            <Activity className="h-3.5 w-3.5" />
            Health Status
          </TabsTrigger>
          <TabsTrigger value="prompt" className="flex items-center gap-1.5">
            <Mic className="h-3.5 w-3.5" />
            System Prompt
          </TabsTrigger>
          <TabsTrigger value="settings" className="flex items-center gap-1.5">
            <Settings className="h-3.5 w-3.5" />
            Settings
          </TabsTrigger>
        </TabsList>

        {/* Health Status Tab */}
        <TabsContent value="health" className="mt-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <Shield className="h-5 w-5" />
                System Health
              </CardTitle>
              <CardDescription>
                Live status of all backend services. Refreshes every 10 seconds.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {healthError ? (
                <div className="space-y-4">
                  <div className="flex items-center justify-between p-4 rounded-lg border border-red-500/25 bg-red-500/5">
                    <div>
                      <p className="font-medium text-sm">Connection Failed</p>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        Cannot reach the backend API. Make sure the server is running
                        on port 8000.
                      </p>
                    </div>
                    <Badge className="bg-red-500/15 text-red-700 border-red-500/25 dark:text-red-400">
                      Offline
                    </Badge>
                  </div>
                </div>
              ) : healthLoading ? (
                <div className="space-y-3">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <div
                      key={i}
                      className="flex items-center justify-between p-3 rounded-lg border"
                    >
                      <Skeleton className="h-4 w-32" />
                      <Skeleton className="h-5 w-16 rounded-full" />
                    </div>
                  ))}
                </div>
              ) : health ? (
                <div className="space-y-3">
                  {/* Overall Status */}
                  <div className="flex items-center justify-between p-4 rounded-lg border bg-muted/30">
                    <div>
                      <p className="font-medium text-sm">Overall Status</p>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        Aggregate system health
                      </p>
                    </div>
                    <StatusBadge status={health.status} />
                  </div>

                  <Separator />

                  {/* Individual Services */}
                  {Object.entries(health.services).map(([key, status]) => (
                    <div
                      key={key}
                      className="flex items-center justify-between p-3 rounded-lg border"
                    >
                      <span className="text-sm font-medium">
                        {serviceLabel(key)}
                      </span>
                      <StatusBadge status={status} />
                    </div>
                  ))}

                  {Object.keys(health.services).length === 0 && (
                    <p className="text-sm text-muted-foreground text-center py-4">
                      No individual service statuses reported.
                    </p>
                  )}
                </div>
              ) : null}
            </CardContent>
          </Card>
        </TabsContent>

        {/* System Prompt Tab */}
        <TabsContent value="prompt" className="mt-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">System Prompt Editor</CardTitle>
              <CardDescription>
                Edit Maya's system prompt to adjust her behavior and personality.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="system-prompt">System Prompt</Label>
                <Textarea
                  id="system-prompt"
                  value={systemPrompt}
                  onChange={(e) => setSystemPrompt(e.target.value)}
                  className="min-h-[320px] font-mono text-sm leading-relaxed resize-y"
                  placeholder="Enter the system prompt for Maya..."
                />
              </div>
              <div className="flex items-center gap-3">
                <Button onClick={handleSavePrompt}>Save Prompt</Button>
                <Button
                  variant="outline"
                  onClick={() => setSystemPrompt(DEFAULT_SYSTEM_PROMPT)}
                >
                  Reset to Default
                </Button>
                {saveMessage && (
                  <span className="text-sm text-emerald-600 dark:text-emerald-400 animate-in fade-in duration-200">
                    {saveMessage}
                  </span>
                )}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Settings Tab */}
        <TabsContent value="settings" className="mt-6">
          <div className="grid gap-6 md:grid-cols-2">
            {/* LLM Settings */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">LLM Configuration</CardTitle>
                <CardDescription>
                  Language model used for conversation
                </CardDescription>
              </CardHeader>
              <CardContent>
                <dl className="space-y-3">
                  <div className="flex justify-between">
                    <dt className="text-sm text-muted-foreground">Model</dt>
                    <dd className="text-sm font-medium font-mono">
                      gpt-oss:20b-cloud
                    </dd>
                  </div>
                  <Separator />
                  <div className="flex justify-between">
                    <dt className="text-sm text-muted-foreground">Provider</dt>
                    <dd className="text-sm font-medium">Ollama (Cloud)</dd>
                  </div>
                  <Separator />
                  <div className="flex justify-between">
                    <dt className="text-sm text-muted-foreground">Base URL</dt>
                    <dd className="text-sm font-medium font-mono">
                      http://localhost:11434
                    </dd>
                  </div>
                  <Separator />
                  <div className="flex justify-between">
                    <dt className="text-sm text-muted-foreground">
                      Function Calling
                    </dt>
                    <dd className="text-sm">
                      <Badge className="bg-emerald-500/15 text-emerald-700 border-emerald-500/25 dark:text-emerald-400">
                        Enabled
                      </Badge>
                    </dd>
                  </div>
                </dl>
              </CardContent>
            </Card>

            {/* VAD Settings */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Voice Activity Detection</CardTitle>
                <CardDescription>Silero VAD configuration</CardDescription>
              </CardHeader>
              <CardContent>
                <dl className="space-y-3">
                  <div className="flex justify-between">
                    <dt className="text-sm text-muted-foreground">Stop Seconds</dt>
                    <dd className="text-sm font-medium font-mono">0.5</dd>
                  </div>
                  <Separator />
                  <div className="flex justify-between">
                    <dt className="text-sm text-muted-foreground">Start Seconds</dt>
                    <dd className="text-sm font-medium font-mono">0.2</dd>
                  </div>
                  <Separator />
                  <div className="flex justify-between">
                    <dt className="text-sm text-muted-foreground">Confidence</dt>
                    <dd className="text-sm font-medium font-mono">0.7</dd>
                  </div>
                  <Separator />
                  <div className="flex justify-between">
                    <dt className="text-sm text-muted-foreground">
                      Turn Detection
                    </dt>
                    <dd className="text-sm font-medium">SmartTurn v3</dd>
                  </div>
                </dl>
              </CardContent>
            </Card>

            {/* STT Settings */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Speech-to-Text</CardTitle>
                <CardDescription>Faster-Whisper multilingual configuration</CardDescription>
              </CardHeader>
              <CardContent>
                <dl className="space-y-3">
                  <div className="flex justify-between">
                    <dt className="text-sm text-muted-foreground">Model</dt>
                    <dd className="text-sm font-medium font-mono">base (multilingual)</dd>
                  </div>
                  <Separator />
                  <div className="flex justify-between">
                    <dt className="text-sm text-muted-foreground">Device</dt>
                    <dd className="text-sm font-medium">CPU</dd>
                  </div>
                  <Separator />
                  <div className="flex justify-between">
                    <dt className="text-sm text-muted-foreground">
                      Compute Type
                    </dt>
                    <dd className="text-sm font-medium font-mono">int8</dd>
                  </div>
                  <Separator />
                  <div className="flex justify-between">
                    <dt className="text-sm text-muted-foreground">Language</dt>
                    <dd className="text-sm font-medium">Auto-detect (Hindi / English)</dd>
                  </div>
                </dl>
              </CardContent>
            </Card>

            {/* TTS Settings */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Text-to-Speech</CardTitle>
                <CardDescription>Sarvam AI multilingual configuration</CardDescription>
              </CardHeader>
              <CardContent>
                <dl className="space-y-3">
                  <div className="flex justify-between">
                    <dt className="text-sm text-muted-foreground">Engine</dt>
                    <dd className="text-sm font-medium">Sarvam AI (bulbul:v3)</dd>
                  </div>
                  <Separator />
                  <div className="flex justify-between">
                    <dt className="text-sm text-muted-foreground">Voice</dt>
                    <dd className="text-sm font-medium font-mono">anushka</dd>
                  </div>
                  <Separator />
                  <div className="flex justify-between">
                    <dt className="text-sm text-muted-foreground">Temperature</dt>
                    <dd className="text-sm font-medium font-mono">0.75</dd>
                  </div>
                  <Separator />
                  <div className="flex justify-between">
                    <dt className="text-sm text-muted-foreground">Languages</dt>
                    <dd className="text-sm font-medium">Hindi (hi-IN) / English (en-IN)</dd>
                  </div>
                  <Separator />
                  <div className="flex justify-between">
                    <dt className="text-sm text-muted-foreground">Runtime</dt>
                    <dd className="text-sm font-medium">Cloud API</dd>
                  </div>
                </dl>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  )
}
