# make pdf      paper/main.pdf
# make arxiv    paper/arxiv.tar.gz, the source package for arXiv
# make figures  redraw the figures from results/figures.json
# make results  rerun analyze.py and mixed.py: results/summary.md, figures.json, mixed.json and mixed.md from results/*.jsonl

pdf:
	$(MAKE) -C paper main.pdf

arxiv:
	$(MAKE) -C paper arxiv

figures:
	$(MAKE) -C paper figures

results:
	python3 analyze.py > /dev/null
	python3 mixed.py > /dev/null

.PHONY: pdf arxiv figures results
