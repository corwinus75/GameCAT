"""Mixiny składające fasadę :class:`gamecat.services.project_service.ProjectService`.

Każdy moduł odpowiada za jeden obszar logiki aplikacji (ustawienia, segmenty,
pliki, TM, QA, glosariusz). Mixiny nie mają własnego stanu – korzystają
z atrybutów inicjalizowanych w ``ProjectService.__init__``.
"""
