import dataclasses
import datetime
import logging
import json
import pathlib
import urllib.request

import appdirs
import yaml

APPNAME = "strsvcp"
APPAUTHOR = "alexpdp7"
USER_DATA_DIR = pathlib.Path(appdirs.user_data_dir(APPNAME, APPAUTHOR))


logger = logging.getLogger(__name__)


def fetch():
    config = load_config()
    for show in config.shows():
        show.save_episode_list(show.fetch_episode_list())


def weekplan():
    config = load_config()
    episodes = []
    for show in config.shows():
        episodes.extend(show.load_episode_list())

    plan = {}

    for episode in episodes:
        isocalendar = episode.airdate.isocalendar()
        year, week = (isocalendar.year, isocalendar.week)

        entry = plan.get((year, week), [])
        plan[(year, week)] = entry
        plan[(year, week)].append(episode)

    this_isocalendar = datetime.date.today().isocalendar()
    this_year, this_week = this_isocalendar.year, this_isocalendar.week

    earlier = []
    for year, week in sorted(plan.keys()):
        if (year, week) <= (this_year, this_week):
            earlier += plan[(year, week)]
        if (year, week) == (this_year, this_week):
            services = {}
            for episode in earlier:
                service_shows = services.get(episode.show.service_name, {})
                service_show_episodes = service_shows.get(episode.show, set())
                service_show_episodes.add(episode)
                service_shows[episode.show] = service_show_episodes
                services[episode.show.service_name] = service_shows
            for service, shows in services.items():
                for show, episodes in shows.items():
                    unseen = (
                        len(episodes) - [s.seen for s in config.shows() if show == s][0]
                    )
                    if unseen > 0:
                        print(service, show.name, unseen)
        if (year, week) > (this_year, this_week):
            week_start = datetime.date.fromisocalendar(year, week, 1)
            week_end = datetime.date.fromisocalendar(year, week, 7)
            service_show_episodes = {}
            for episode in plan[(year, week)]:
                show = episode.show.name
                service = episode.show.service_name
                service_show_episodes[service] = service_show_episodes.get(
                    service, dict()
                )
                service_show_episodes[service][show] = (
                    service_show_episodes[service].get(show, 0) + 1
                )
            print(week_start, week_end, service_show_episodes)


@dataclasses.dataclass(frozen=True)
class Show:
    name: str
    service_name: str
    tvmaze_id: int
    seen: int

    def fetch_episode_list(self):
        url = f"https://api.tvmaze.com/shows/{self.tvmaze_id}/episodes"
        logging.debug("fetching %s for %s", url, self)
        request = urllib.request.Request(url=url)
        with urllib.request.urlopen(request) as f:
            logging.debug("%s returned %s", url, f.status)
            assert f.status == 200
            return json.loads(f.read())

    def episode_list_path(self) -> pathlib.Path:
        return USER_DATA_DIR / "shows" / f"{self.tvmaze_id}.json"

    def save_episode_list(self, data):
        path = self.episode_list_path()
        logging.debug("saving data to %s", path)
        path.parent.mkdir(exist_ok=True, parents=True)
        path.write_text(json.dumps(data))

    def load_episode_list(self):
        return to_episode_list(json.loads(self.episode_list_path().read_text()), self)


@dataclasses.dataclass(frozen=True)
class Episode:
    show: Show
    airdate: datetime.date
    season: int
    episode: int


def to_episode_list(data, show):
    episodes = []
    for episode in data:
        episodes.append(
            Episode(
                show=show,
                airdate=datetime.date.fromisoformat(episode["airdate"]),
                season=int(episode["season"]),
                episode=int(episode["number"]),
            )
        )
    return episodes


class Config:
    def __init__(self, data):
        self.data = data

    def shows(self):
        return [
            Show(
                name=show_name,
                service_name=service_name,
                tvmaze_id=int(show_data["tvmaze"]),
                seen=int(show_data.get("seen", 0)),
            )
            for service_name, shows in self.data.items()
            for show_name, show_data in shows.items()
        ]


def load_config() -> Config:
    return Config(yaml.load(pathlib.Path("example.yaml").read_text(), yaml.SafeLoader))
