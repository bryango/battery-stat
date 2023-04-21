#!/usr/bin/env python3
# Battery statistics

# %% Setup
BATTERY_HISTORY_FILE_GLOB = "history-charge-*"
BATTERY_STAT_PATH = "/var/lib/upower/"
BATTERY_MAX_CHARGE = 85

PLOT_RANGE = 36
DEFAULT_HISTORY_MIN = 0
DEFAULT_HISTORY_MAX = 12


from pathlib import Path
from datetime import datetime, timedelta
import math as m
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.widgets import Slider, Button, RadioButtons  # type: ignore
# import sys

AN_HOUR = timedelta(hours=1)
A_DAY = timedelta(days=1)


# %% Prepare data
data_path = Path(BATTERY_STAT_PATH)
data_files = list(
    data_path.glob('**/' + BATTERY_HISTORY_FILE_GLOB)
)

if not data_files:
    print(
        '### Battery data NOT found, search path:',
        BATTERY_STAT_PATH + BATTERY_HISTORY_FILE_GLOB
    )
    exit(1)
else:
    print('### Battery data found:\n')
    print(*[
        '    * ' + str(file.relative_to(data_path))
        for file in data_files
    ])
    print('')

num_data_files = len(data_files)
if num_data_files == 1:
    data_file = data_files[-1]
else:
    def choose_file():
        try:
            idx = input(f'### Choose data file [1 ~ {num_data_files}]'
                        f', defaults to the last item: ')
            if not idx:
                idx = num_data_files
            idx = int(idx) - 1
            if idx not in range(num_data_files):
                raise IndexError
        except (ValueError, IndexError, TypeError):
            print('')
            print('### Illegal index, try again!')
            return choose_file()

        return data_files[idx]

    data_file = choose_file()

with open(data_file, 'r') as file:
    data = file.read()

data_sheet = [ line.split('\t') for line in data.splitlines() ]
data_sheet = [
    [
        int(line[0]),   # Unix time
        float(line[1])  # Charge percentage
    ] for line in data_sheet
]

# Remove 'unknown' status
data_sheet = [ line for line in data_sheet if line[2] != 'unknown' ]
timeline, charge_data = tuple(zip(*data_sheet))[:2]
current_charge = charge_data[-1]

# Compressed timeline
MAX_GAP = .2 * AN_HOUR.total_seconds()
timeline_zipped = list(timeline)
for idx in range(1, len(timeline_zipped)):
    delta = timeline_zipped[idx] - timeline_zipped[idx - 1]
    if delta > MAX_GAP:
        timeline_zipped[:idx] = [
            timestamp + delta - MAX_GAP
            for timestamp in timeline_zipped[:idx]
        ]

print('### Data prepared, plotting ...')


# %% Initialize graph
fig, ax = plt.subplots()
fig.canvas.manager.set_window_title(data_file.name)  # type: ignore
plt.subplots_adjust(left=.1, bottom=.3)

# Slider controls
ax_history_max, ax_history_min = [
    plt.axes((.2, y_pos, .6, 0.03))
    for y_pos in [.15, .1]
]
slider_history_max, slider_history_min = list(map(
    lambda args: Slider(*args[:2], - PLOT_RANGE, 0, **args[-1]),
    [
        [ax_history_max, 'From', {
            'valinit': - DEFAULT_HISTORY_MAX
        }],
        [ax_history_min, 'To', {
            'valinit': DEFAULT_HISTORY_MIN
        }]
    ]
))

# Reset button
ax_reset = plt.axes((0.8, 0.025, 0.1, 0.04))
button_reset = Button(
    ax_reset, 'Reset', hovercolor='0.975'
)

# Switches
ax_switch = plt.axes((0.15, 0.35, 0.2, 0.15))
switch_button = RadioButtons(
    ax_switch, (
        'Compressed',
        'Relative',
        'Absolute'
    ), active=0
)


# %% Time processing
def midnight_timestamp(timestamp):
    return datetime.fromtimestamp(timestamp).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).timestamp()


def timestamp_now():
    return datetime.now().timestamp()


TICK_INTERVAL = timedelta(minutes=5)


def ticks_format(
    range_min, range_max,
    compress=True,
    relative=True
):
    t_min, t_max = [
        datetime.fromtimestamp(t)
        for t in (range_min, range_max)
    ]
    t_delta = t_max - t_min
    t_days = m.ceil(t_delta / A_DAY) + 1
    # +1 day to compensate for rollback to midnight

    def date_loc(count):
        return (
            midnight_timestamp(range_min)
            + (A_DAY * count).total_seconds()
        )

    def time_loc(count):
        return (
            midnight_timestamp(range_min)
            + (TICK_INTERVAL * count).total_seconds()
        ) if not relative else (
            timestamp_now()
            - (TICK_INTERVAL * count).total_seconds()
        )  # relative timestamp

    ax.xaxis.set_major_locator(ticker.FixedLocator([
        time_loc(count)
        for count in range(
            round((t_days + 1) * (A_DAY / TICK_INTERVAL))
        )
        if range_min < time_loc(count) < range_max
    ], nbins=12))  # show date at 0:00

    ax.xaxis.set_major_formatter(ticker.FuncFormatter(
        lambda timestamp, pos:
        datetime.fromtimestamp(timestamp).strftime(
            '%-H:%M'
        ) if not relative else "{:.1f}".format(
            (datetime.fromtimestamp(timestamp) - datetime.now())
            / AN_HOUR
        )
    ))

    if compress:
        ax.xaxis.set_minor_locator(ticker.NullLocator())
    else:
        ax.xaxis.set_minor_locator(ticker.FixedLocator([
            date_loc(count)
            for count in range(t_days + 1)
            if range_min <= date_loc(count) <= range_max
        ]))  # show date at 0:00 midnight

        ax.xaxis.set_minor_formatter(ticker.FuncFormatter(
            lambda timestamp, pos:
            datetime.fromtimestamp(timestamp).strftime(
                "%-m/%-d"
            )
        ))

        ax.tick_params(which='minor', direction='in')
        plt.setp(ax.xaxis.get_minorticklabels(), position=(0, +.085))


class BatteryStat(object):
    def __init__(self):
        slider_history_max.on_changed(self.update)
        slider_history_min.on_changed(self.update)
        switch_button.on_clicked(self.update)

        button_reset.on_clicked(self.reset)

        # Defaults
        self.compress = True
        self.relative = True

        self.format()

    def format(
        self,
        compress=None,
        relative=None,
        ticks_format=ticks_format,
        min_max_history=(
            DEFAULT_HISTORY_MIN,
            DEFAULT_HISTORY_MAX
        )  # in hours
    ):
        # Clear graph
        ax.clear()

        self.ticks_format = ticks_format
        options = {
            'compress': compress,
            'relative': relative
        }
        for key, value in options.items():
            if value is not None:
                setattr(self, key, value)

        # Time in seconds
        if self.compress:
            timeline_local = timeline_zipped
            now = timeline_local[-1]
        else:
            timeline_local = timeline
            now = timestamp_now()

        t_end, t_start = [
            now - timedelta(hours=hours).total_seconds()
            for hours in min_max_history
        ]
        # Set plot range
        self.plot_range = [t_start, t_end]
        ax.set_xlim(self.plot_range)  # type: ignore

        # New data
        new_data = [
            [ time, charge_data[idx] ]
            for idx, time in enumerate(timeline_local)
            if t_start <= time <= t_end
        ]
        if not new_data:
            self.timeline = self.charge_data = []
        else:
            self.timeline, self.charge_data = list(zip(*new_data))

    def analyze(self):
        timeline, charge_data = self.timeline, self.charge_data

        if len(timeline) <= 2 or not all(
            x <= y for x, y in zip(charge_data, charge_data[1:])
        ) and not all(
            x >= y for x, y in zip(charge_data, charge_data[1:])
        ):  # not monotonic data
            self._set_title(
                'Charge Data\n'
                '[select monotonic domain for statistics]'
            )
            return

        # Time range in hours
        t_range = (timeline[-1] - timeline[0]) / AN_HOUR.total_seconds()

        # Statistics
        rate = (charge_data[-1] - charge_data[0]) / t_range
        life = BATTERY_MAX_CHARGE / abs(rate)
        full_life = 100. / abs(rate)

        status = data_sheet[-1][-1]
        if status == 'discharging':
            left = current_charge / abs(rate)
        elif status == 'charging':
            left = (BATTERY_MAX_CHARGE - current_charge) / abs(rate)
        else:
            left = None

        left_string = f' | remaining: {left:.1f}' \
            if left is not None else ''

        # Set title
        self._set_title(
            f'rate: {rate:.2f}%'
            f' | max: {BATTERY_MAX_CHARGE}%\n'
            f'life: {life:.1f}'
            f' | full: {full_life:.1f}' + left_string
        )
        self._plot_trend()

    def _set_title(self, title: str):
        ax.set_title(
            title,
            y=1.015,
            fontdict={
                'family': 'monospace'
            },
            linespacing=1.25
        )

    def _plot_trend(self):
        ax.plot(
            *[ [ pts[0], pts[-1] ]
               for pts in [self.timeline, self.charge_data] ],
            linewidth=.5,
            dashes=[24, 8],
            color='grey'
        )

    def graph(self):
        self.analyze()
        self.ticks_format(
            *self.plot_range,
            compress=self.compress,
            relative=self.relative
        )
        ax.scatter(
            self.timeline, self.charge_data,
            s=8
        )

    def update(self, value):
        min_history = - slider_history_min.val
        max_history = - slider_history_max.val
        if min_history >= max_history:
            max_history = min_history + .1
            slider_history_max.set_val(-max_history)

        options = {}

        if value == 'Compressed':
            options.update({
                'compress': True,
                'relative': True
            })
        if value == 'Relative':
            options.update({
                'compress': False,
                'relative': True
            })
        if value == 'Absolute':
            options.update({
                'compress': False,
                'relative': False
            })

        self.format(
            min_max_history=(min_history, max_history),
            **options
        )
        self.graph()
        fig.canvas.draw_idle()

    def reset(self, event):
        slider_history_max.reset()
        slider_history_min.reset()


stat = BatteryStat()
stat.graph()
plt.show()
