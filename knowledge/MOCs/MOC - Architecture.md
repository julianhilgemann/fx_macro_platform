---
title: MOC - Architecture
type: moc
status: growing
tags: [moc, architecture]
created: 2026-09-18
updated: 2026-09-18
aliases: [Architecture MOC]
---

# MOC - Architecture

How to describe a system, how to decide about it, and how to shape its
boundaries. These notes are the vocabulary for the conversations this platform is
built to have.

## Describing

- [[C4 Model]], four zoom levels for drawing a system so different audiences can
 read it. L1 context and L2 container are the two worth drawing first.
- [[Architecture Decision Records]], one short file per significant decision,
 immutable, with the reasoning that is otherwise lost within a month.

## Shaping

- [[Domain-Driven Design]], aligning software boundaries with the domain, and the
 language the domain actually uses.
- [[Hexagonal Architecture]], keeping the domain independent of its transports
 and storage.
- [[Event-Driven Architecture]], components reacting to facts rather than being
 called.
- [[CQRS]], separating the write model from the read model when their needs
 genuinely diverge.

## Where the platform stands

[[FX Macro Platform]] is layered rather than event-driven: a batch pipeline with
clear stages and a serving layer on top. That is the right shape for daily macro
data. [[Event-Driven Architecture]] and [[CQRS]] are worth understanding but are
not justified here yet, and adopting them would be exactly the "stop tinkering"
failure mode the plan warns against.

G1 in [[Platform Delivery Plan]] is where this map gets used: C4 L1 and L2
diagrams, and a `docs/adr/` folder that does not exist yet.

## Reading order

[[C4 Model]] and [[Architecture Decision Records]] are immediately actionable and
cheap. The other four are background reading.

## Related

- [[MOC - Platform Engineering]]
- [[MOC - Data Engineering]]
- [[Platform Delivery Plan]]
- [[Current State]]
