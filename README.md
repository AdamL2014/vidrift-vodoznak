# VidRift – vodoznak

Každých 5 minut se tady spustí GitHub Action, která do nově nahraných videí na VidRiftu vypálí vodoznak
(logo + @kanál, jako TikTok). Video uvidí ostatní až potom.

Potřebná tajná hodnota: **WORKER_TOKEN** (Settings → Secrets and variables → Actions). Stejná hodnota musí být v Supabase → Edge Functions → Secrets.
