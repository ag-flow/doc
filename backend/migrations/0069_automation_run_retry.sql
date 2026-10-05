-- =====================================================================
-- 0069_automation_run_retry.sql — reprise persistante des émissions échouées
-- du chemin automate → ragflow (bug « corpus qui dérive en silence »).
--
-- Avant : un POST en échec était historisé `failed` mais le curseur avançait
-- quand même → l'écriture n'était JAMAIS rejouée (perte silencieuse). Le ticket
-- exige qu'« une écriture non indexée soit rattrapable » : il faut un état
-- persistant qui porte la reprise. On l'ajoute sur automation_run.
--
-- `attempts` : nombre de tentatives d'émission (1 à la première). Une passe de
-- retry (worker) réessaie les runs `failed` non dead-letter à chaque tick.
-- `dead_letter` : au-delà de MAX_ATTEMPTS (ou event purgé), la ligne est marquée
-- pour inspection et cesse d'être réessayée — elle n'est plus « active », mais
-- reste visible (à la différence d'une perte silencieuse).
-- =====================================================================

ALTER TABLE automation_run ADD COLUMN attempts integer NOT NULL DEFAULT 1;
ALTER TABLE automation_run ADD COLUMN dead_letter boolean NOT NULL DEFAULT false;

-- Passe de retry : retrouver vite les émissions échouées ENCORE à rejouer.
CREATE INDEX idx_automation_run_retry ON automation_run (automation_ref, event_seq)
    WHERE status = 'failed' AND dead_letter = false AND event_seq IS NOT NULL;
