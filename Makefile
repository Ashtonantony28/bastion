# Report targets regenerate every number in docs/results from the lakehouse ($BASTION_DATA).
.PHONY: test ci-build report-m6 report-m7 report-svb report-ews report-m4 report-m5

test:
	pytest -q && bastion fixtures --check

ci-build:
	bastion build --target ci

report-m7:
	bastion report m7

report-ews:
	bastion report ews

report-svb:
	bastion report svb

report-m6:
	bastion report alm

report-m4:
	bastion report market

report-m5:
	bastion report ccr
