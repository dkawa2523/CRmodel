# Design Review from Three Viewpoints

## 1. Software architect viewpoint

### What was improved

- configuration concerns are now isolated from physics through normalization
- project-level execution is now available through a single manifest
- repetitive YAML can be reduced using `include`, `files_glob`, and `parameter_groups`
- a public `oescr.api` makes module boundaries explicit
- documentation is no longer concentrated in one short README

### What is still intentionally simple

- the code uses dictionaries rather than a full pydantic/dataclass schema graph
- plugin discovery is explicit rather than dynamic

That is a good trade for a research codebase whose users are expected to inspect and modify it.

## 2. Simulation engineer viewpoint

### What was improved

- forward and inverse runs can now be driven from `project.yaml`
- benchmark examples are easier to clone and modify because `case_init.yaml` only overrides truth/base values
- inverse setup is shorter and less error-prone because shell arrays can be declared once with `parameter_groups`
- measurement sets can be loaded with one glob instead of repeated file lists
- validation is now run after normalization, which catches more user errors in practice

### Remaining cautions

- the code is still a scaffold and expects users to inspect real-data assumptions
- not all physical parameters have strong validators because real labs use heterogeneous conventions

## 3. Physicist viewpoint

### What was improved

- the theory, approximations, and numerical choices are now documented in separate markdown files
- the reduced CR kernel, band emitters, geometry, and instrument model are easier to inspect separately
- each physics block can be reused without the full inverse stack
- the low-resolution EEDF restriction is now clearer and easier to audit

### Remaining cautions

- reduced CR is still not a substitute for a full chemistry + transport + wall model
- effective bands remain empirical or semi-empirical surrogates
- uncertainty treatment is still approximate

Overall, the code is now much closer to a maintainable research platform than a one-off script collection.
