# make          main.pdf, redrawing the figures first when the results or figures.py changed
# make figures  redraw paper/figures/*.pdf (and the README's figures/*.png) from results/
# make arxiv    arxiv.tar.gz: the source arXiv compiles, with the .bbl (arXiv does not run BibTeX)
# make clean    remove LaTeX by-products, main.pdf and the tarball
#
# acl.sty and acl_natbib.bst: github.com/acl-org/acl-style-files at d5adc823ff0f80f98c80405ca0ab66c68e684409

FIGURES = figures/fig-moral.pdf figures/fig-classification.pdf figures/fig-benchmarks.pdf figures/fig-lean.pdf figures/fig-bbq-categories.pdf figures/fig-decision.pdf

main.pdf: main.tex references.bib acl.sty acl_natbib.bst $(FIGURES)
	latexmk -pdf -halt-on-error -interaction=nonstopmode main.tex

# one run of figures.py draws all six; the other five ride on the first (macOS make 3.81 has no grouped targets)
figures/fig-moral.pdf: figures.py ../results/figures.json ../analyze.py
	cd .. && python3 paper/figures.py
figures/fig-classification.pdf figures/fig-benchmarks.pdf figures/fig-lean.pdf figures/fig-bbq-categories.pdf figures/fig-decision.pdf: figures/fig-moral.pdf

figures:
	cd .. && python3 paper/figures.py

arxiv.tar.gz: main.pdf
	COPYFILE_DISABLE=1 tar -czf $@ main.tex main.bbl references.bib acl.sty acl_natbib.bst $(FIGURES)

arxiv: arxiv.tar.gz

clean:
	latexmk -C main.tex
	rm -f main.bbl arxiv.tar.gz

.PHONY: figures arxiv clean
