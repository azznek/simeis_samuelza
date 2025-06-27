name: Bug Report
description: Signaler un bug dans le projet
title: "[BUG] "
labels: [bug]

body:
  - type: textarea
    attributes:
      label: Description du bug
    validations:
      required: true
  - type: textarea
    attributes:
      label: Étapes pour reproduire
    validations:
      required: true
  - type: input
    attributes:
      label: Environnement (OS, version...)
