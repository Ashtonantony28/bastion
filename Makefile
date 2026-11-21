# Report targets regenerate every number in docs/results from the lakehouse ($BASTION_DATA).
.PHONY: test ci-build report-m7 report-svb report-ews

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
