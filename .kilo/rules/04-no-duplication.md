# No Duplication Rule

Never create:
- a second mutation service
- a second version history system
- a second results persistence scheme
- a second compare pipeline
- duplicate pages with overlapping responsibility
- duplicate route families with slightly different naming

Before adding anything new, explicitly answer:
- what existing file is closest to owning this responsibility?
- why can it not be extended safely?
- what exact duplication or conflict would happen if I add a new file or route?

If that answer is weak, extend the existing implementation instead.