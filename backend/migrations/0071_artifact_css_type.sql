-- =====================================================================
-- 0071_artifact_css_type.sql  (additif, seed)
-- Autorise l'extension `css` dans le registre des types d'artefact, pour la
-- feature « Base CSS des maquettes (mockup-base) » : la base est un artefact
-- MUTABLE `text/css` (sa révision = sa version), dont le contenu est ensuite
-- embarqué verbatim dans les maquettes HTML.
--
-- `text/css` n'est PAS dans la denylist applicative (contrairement à text/html
-- et aux types actifs) : c'est un contenu textuel inerte. Il n'est jamais servi
-- inline depuis l'origine docflow — la base vit embarquée dans le HTML de la
-- maquette, pas servie telle quelle.
--
-- ON CONFLICT DO NOTHING → rejouable sur base vierge comme existante.
-- =====================================================================

INSERT INTO artifact_media_type (extension, media_type, label) VALUES
    ('css', 'text/css', 'Feuille de style CSS')
ON CONFLICT (extension) DO NOTHING;
