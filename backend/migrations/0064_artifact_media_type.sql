-- Registre administrable des types de fichiers acceptés comme artefacts
-- (auparavant en dur dans le code, ALLOWED_MEDIA_TYPES). L'admin gère la liste
-- depuis une page dédiée ; l'éditeur la consomme pour proposer un type au
-- collage. Un denylist EN DUR (côté applicatif) reste la garde de sécurité :
-- aucun type actif (text/html…) ne peut être ajouté, quoi qu'il arrive ici.
CREATE TABLE IF NOT EXISTS artifact_media_type (
    extension   text PRIMARY KEY
                CHECK (extension ~ '^[a-z0-9]{1,16}$'),
    media_type  text NOT NULL
                CHECK (char_length(media_type) BETWEEN 1 AND 200),
    label       text NOT NULL DEFAULT ''
                CHECK (char_length(label) <= 100),
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

-- Seed = whitelist historique. ON CONFLICT DO NOTHING → rejouable sur base
-- vierge comme sur base existante, sans écraser d'éventuelles modifications.
INSERT INTO artifact_media_type (extension, media_type, label) VALUES
    ('png',  'image/png',        'Image PNG'),
    ('jpg',  'image/jpeg',       'Image JPEG'),
    ('jpeg', 'image/jpeg',       'Image JPEG'),
    ('gif',  'image/gif',        'Image GIF'),
    ('webp', 'image/webp',       'Image WebP'),
    ('svg',  'image/svg+xml',    'Image SVG'),
    ('pdf',  'application/pdf',  'Document PDF'),
    ('txt',  'text/plain',       'Texte brut'),
    ('md',   'text/markdown',    'Markdown'),
    ('csv',  'text/csv',         'CSV'),
    ('json', 'application/json', 'JSON'),
    ('vtt',  'text/vtt',         'Sous-titres WebVTT'),
    ('mp3',  'audio/mpeg',       'Audio MP3'),
    ('wav',  'audio/wav',        'Audio WAV'),
    ('m4a',  'audio/mp4',        'Audio M4A'),
    ('ogg',  'audio/ogg',        'Audio OGG'),
    ('mp4',  'video/mp4',        'Vidéo MP4'),
    ('webm', 'video/webm',       'Vidéo WebM'),
    ('zip',  'application/zip',  'Archive ZIP'),
    ('docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',   'Word (docx)'),
    ('xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',         'Excel (xlsx)'),
    ('pptx', 'application/vnd.openxmlformats-officedocument.presentationml.presentation', 'PowerPoint (pptx)')
ON CONFLICT (extension) DO NOTHING;
