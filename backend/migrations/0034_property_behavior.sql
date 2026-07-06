-- =====================================================================
-- 0034 — Comportements de propriété (MPTS).
--
-- behavior marque une propriété gérée automatiquement par le serveur :
--   auto_now        : date courante posée à CHAQUE enregistrement du
--                     document (création, contenu/titre, valeurs de props) ;
--   auto_now_create : date courante posée à la création, jamais retouchée.
-- Réservé aux propriétés de type 'date' (invariant applicatif, validé
-- par properties/service.py et l'import de templates).
-- Une propriété à behavior est refusée en écriture manuelle.
-- =====================================================================

ALTER TABLE properties_defs
    ADD COLUMN behavior text NULL
        CHECK (behavior IN ('auto_now', 'auto_now_create'));
