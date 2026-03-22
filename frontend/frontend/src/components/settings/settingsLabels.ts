export const SETTINGS_LABELS = {
  model_primary: {
    label: 'Modello Principale',
    description: 'Modello usato per ragionamento e generazione risposte',
    tooltip: 'Questo modello gestisce la maggior parte delle interazioni. Scegli un modello locale per privacy e velocità, o cloud per capacità avanzate.',
    example: 'Es: Qwen 3.5 4B (veloce, locale) o Mistral Large (potente, cloud)',
  },
  model_routing: {
    label: 'Modello di Routing',
    description: 'Classifica le intenzioni dell\'utente per instradare la richiesta',
    tooltip: 'Un modello veloce che determina quale strumento o specialista usare. Di solito un modello piccolo locale.',
    example: 'Es: Qwen 3.5 4B - ottimo per classificazione rapida',
  },
  model_synthesis: {
    label: 'Modello di Sintesi',
    description: 'Riassume e combina risultati da più fonti',
    tooltip: 'Usato per unificare risposte da tool multipli o creare riassunti.',
    example: 'Es: Qwen 3.5 4B o modello cloud per sintesi complesse',
  },
  model_fallback: {
    label: 'Modello di Riserva',
    description: 'Modello cloud usato quando il locale non è disponibile',
    tooltip: 'Attivato automaticamente se il modello locale fallisce o le risorse sono insufficienti.',
    example: 'Es: Mistral Large 3 via NanoGPT',
  },
  temperature: {
    label: 'Temperatura',
    description: 'Controlla la creatività delle risposte',
    tooltip: 'Valori bassi (0.1-0.3) = risposte coerenti e prevedibili. Valori alti (0.7-1.0) = risposte creative e varie.',
    example: '0.3 = bilanciato, 0.1 = preciso, 0.7 = creativo',
  },
  max_tokens: {
    label: 'Token Massimi',
    description: 'Lunghezza massima della risposta generata',
    tooltip: 'Più token = risposte più lunghe ma più lente. Un token ≈ 4 caratteri in italiano.',
    example: '2048 = risposta breve, 8192 = risposta dettagliata',
  },
  context_window: {
    label: 'Finestra di Contesto',
    description: 'Memoria disponibile per la conversazione',
    tooltip: 'Quanti token di conversazione precedente il modello può ricordare. Più alto = più memoria, ma richiede più RAM.',
    example: '16384 = conversazione lunga, 32768 = memoria estesa',
  },
  use_local_tool_calling: {
    label: 'Esecuzione Tool Locale',
    description: 'Esegui le chiamate agli strumenti localmente invece che nel cloud',
    tooltip: 'ON = più privacy e velocità, OFF = usa il cloud per tool complessi.',
    example: 'Consigliato ON per la maggior parte degli utilizzi',
  },
  enable_streaming: {
    label: 'Risposte in Streaming',
    description: 'Mostra le risposte mentre vengono generate',
    tooltip: 'ON = vedi la risposta apparire parola per parola, OFF = attendi la risposta completa.',
    example: 'Consigliato ON per esperienza più reattiva',
  },
  enable_caching: {
    label: 'Cache Risposte',
    description: 'Memorizza risposte frequenti per accesso più veloce',
    tooltip: 'ON = risposte identiche vengono riutilizzate, OFF = ogni richiesta è elaborata da zero.',
    example: 'Consigliato ON per risparmiare tempo e costi',
  },
  enable_metrics: {
    label: 'Metriche Prestazioni',
    description: 'Raccogli statistiche dettagliate sulle prestazioni',
    tooltip: 'ON = traccia tempi di risposta, uso memoria, ecc. Utile per debugging.',
    example: 'Consigliato OFF per uso normale, ON per analisi',
  },
  context_overflow_strategy: {
    label: 'Strategia Overflow Contesto',
    description: 'Come gestire conversazioni troppo lunghe',
    tooltip: 'Determina cosa fare quando la conversazione supera la memoria disponibile.',
    example: 'Vedi opzioni dettagliate sotto',
  },
} as const;

export const OVERFLOW_STRATEGIES_IT = [
  {
    value: 'map_reduce',
    label: 'Map-Reduce',
    description: 'Divide il contesto in parti, le elabora in parallelo, unisce i risultati',
    tooltip: 'Mantiene tutte le informazioni ma richiede più elaborazione. Ideale per documenti lunghi.',
    recommended: true,
  },
  {
    value: 'truncate',
    label: 'Troncamento',
    description: 'Mantiene i messaggi più recenti, scarta il contesto più vecchio',
    tooltip: 'Veloce ma perde informazioni. Utile per conversazioni brevi.',
    recommended: false,
  },
  {
    value: 'cloud_fallback',
    label: 'Fallback Cloud',
    description: 'Passa a un modello cloud con finestra di contesto più grande',
    tooltip: 'Usa il cloud solo quando necessario. Richiede connessione internet.',
    recommended: false,
  },
] as const;

export const FEATURE_FLAGS_IT = [
  {
    key: 'useLocalToolCalling',
    label: 'Esecuzione Tool Locale',
    description: 'Esegui le chiamate agli strumenti localmente invece che nel cloud',
    tooltip: SETTINGS_LABELS.use_local_tool_calling.tooltip,
    default: true,
  },
  {
    key: 'enableStreaming',
    label: 'Risposte in Streaming',
    description: 'Mostra le risposte mentre vengono generate in tempo reale',
    tooltip: SETTINGS_LABELS.enable_streaming.tooltip,
    default: true,
  },
  {
    key: 'enableCaching',
    label: 'Cache Risposte',
    description: 'Memorizza risposte frequenti per accesso più veloce',
    tooltip: SETTINGS_LABELS.enable_caching.tooltip,
    default: true,
  },
  {
    key: 'enableMetrics',
    label: 'Metriche Prestazioni',
    description: 'Raccogli statistiche dettagliate sulle prestazioni del sistema',
    tooltip: SETTINGS_LABELS.enable_metrics.tooltip,
    default: false,
  },
] as const;

export const TOGGLE_LABELS = {
  on: 'ON',
  off: 'OFF',
} as const;
