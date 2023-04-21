# battery-stat
visualize battery statistics for linux

## install & run

- The plot is generated with `matplotlib`.
- To automate the install, use [**pipx**](https://pypa.github.io/pipx/). Believe me, it's worth it!
- With `pipx` in hand,

```
pipx install git+https://github.com/bryango/battery-stat.git
battery-stat
```

## develop

```
poetry update --no-dev -vv
poetry run battery-stat
```
