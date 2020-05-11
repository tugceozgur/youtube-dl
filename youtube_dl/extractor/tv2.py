# coding: utf-8
from __future__ import unicode_literals

import re

from .common import InfoExtractor
from ..compat import compat_HTTPError
from ..utils import (
    determine_ext,
    ExtractorError,
    int_or_none,
    float_or_none,
    js_to_json,
    parse_iso8601,
    remove_end,
    strip_or_none,
    try_get,
)


class TV2IE(InfoExtractor):
    _VALID_URL = r'https?://(?:www\.)?tv2\.no/v/(?P<id>\d+)'
    _TEST = {
        'url': 'http://www.tv2.no/v/916509/',
        'info_dict': {
            'id': '916509',
            'ext': 'flv',
            'title': 'Se Frode Gryttens hyllest av Steven Gerrard',
            'description': 'TV 2 Sportens huspoet tar avskjed med Liverpools kaptein Steven Gerrard.',
            'timestamp': 1431715610,
            'upload_date': '20150515',
            'duration': 156.967,
            'view_count': int,
            'categories': list,
        },
    }
    _API_DOMAIN = 'sumo.tv2.no'
    _PROTOCOLS = ('HDS', 'HLS', 'DASH')
    _GEO_COUNTRIES = ['NO']

    def _real_extract(self, url, website=''):
        video_id = self._match_id(url)
        api_base = 'http://%s/api/web/asset/%s' % (self._API_DOMAIN, video_id)

        formats = []
        format_urls = []
        for protocol in self._PROTOCOLS:
            try:
                data = self._download_json(
                    api_base + '/play.json?protocol=%s&videoFormat=SMIL+ISMUSP' % protocol,
                    video_id, 'Downloading play JSON')['playback']
            except ExtractorError as e:
                if isinstance(e.cause, compat_HTTPError) and e.cause.code == 401:
                    error = self._parse_json(e.cause.read().decode(), video_id)['error']
                    error_code = error.get('code')
                    if error_code == 'ASSET_PLAYBACK_INVALID_GEO_LOCATION':
                        self.raise_geo_restricted(countries=self._GEO_COUNTRIES)
                    elif error_code == 'SESSION_NOT_AUTHENTICATED':
                        self.raise_login_required()
                    raise ExtractorError(error['description'])
                raise
            items = try_get(data, lambda x: x['items']['item'])
            if not items:
                continue
            if not isinstance(items, list):
                items = [items]
            for item in items:
                if not isinstance(item, dict):
                    continue
                video_url = item.get('url')
                if not video_url or video_url in format_urls:
                    continue
                format_id = '%s-%s' % (protocol.lower(), item.get('mediaFormat'))
                if not self._is_valid_url(video_url, video_id, format_id):
                    continue
                format_urls.append(video_url)
                ext = determine_ext(video_url)
                if ext == 'f4m':
                    formats.extend(self._extract_f4m_formats(
                        video_url, video_id, f4m_id=format_id, fatal=False))
                elif ext == 'm3u8':
                    if not data.get('drmProtected'):
                        formats.extend(self._extract_m3u8_formats(
                            video_url, video_id, 'mp4', entry_protocol='m3u8_native',
                            m3u8_id=format_id, fatal=False))
                elif ext == 'mpd':
                    formats.extend(self._extract_mpd_formats(
                        video_url, video_id, format_id, fatal=False))
                elif ext == 'ism' or video_url.endswith('.ism/Manifest'):
                    pass
                else:
                    formats.append({
                        'url': video_url,
                        'format_id': format_id,
                        'tbr': int_or_none(item.get('bitrate')),
                        'filesize': int_or_none(item.get('fileSize')),
                    })
        if not formats and data.get('drmProtected'):
            raise ExtractorError('This video is DRM protected.', expected=True)
        self._sort_formats(formats)

        asset = self._download_json(
            api_base + '.json', video_id,
            'Downloading metadata JSON')['asset']
        title = asset['title']

        thumbnails = [{
            'id': thumbnail.get('@type'),
            'url': thumbnail.get('url'),
        } for _, thumbnail in (asset.get('imageVersions') or {}).items()]

        return {
            'id': video_id,
            'url': video_url,
            'title': title,
            'description': strip_or_none(asset.get('description')),
            'thumbnails': thumbnails,
            'timestamp': parse_iso8601(asset.get('createTime')),
            'duration': float_or_none(asset.get('accurateDuration') or asset.get('duration')),
            'view_count': int_or_none(asset.get('views')),
            'categories': asset.get('keywords', '').split(','),
            'formats': formats,
        }


class TV2ArticleIE(InfoExtractor):
    _VALID_URL = r'https?://(?:www\.)?tv2\.no/(?:a|\d{4}/\d{2}/\d{2}(/[^/]+)+)/(?P<id>\d+)'
    _TESTS = [{
        'url': 'http://www.tv2.no/2015/05/16/nyheter/alesund/krim/pingvin/6930542',
        'info_dict': {
            'id': '6930542',
            'title': 'Russen hetses etter pingvintyveri - innrømmer å ha åpnet luken på buret',
            'description': 'De fire siktede nekter fortsatt for å ha stjålet pingvinbabyene, men innrømmer å ha åpnet luken til de små kyllingene.',
        },
        'playlist_count': 2,
    }, {
        'url': 'http://www.tv2.no/a/6930542',
        'only_matching': True,
    }]

    def _real_extract(self, url, website=''):
        playlist_id = self._match_id(url)

        webpage = self._download_webpage(url, playlist_id, website=website)

        # Old embed pattern (looks unused nowadays)
        assets = re.findall(r'data-assetid=["\'](\d+)', webpage)

        if not assets:
            # New embed pattern
            for v in re.findall(r'(?s)TV2ContentboxVideo\(({.+?})\)', webpage):
                video = self._parse_json(
                    v, playlist_id, transform_source=js_to_json, fatal=False)
                if not video:
                    continue
                asset = video.get('assetId')
                if asset:
                    assets.append(asset)

        entries = [
            self.url_result('http://www.tv2.no/v/%s' % asset_id, 'TV2')
            for asset_id in assets]

        title = remove_end(self._og_search_title(webpage), ' - TV2.no')
        description = remove_end(self._og_search_description(webpage), ' - TV2.no')

        return self.playlist_result(entries, playlist_id, title, description)


class KatsomoIE(TV2IE):
    _VALID_URL = r'https?://(?:www\.)?(?:katsomo|mtv)\.fi/(?:#!/)?(?:[^/]+/[0-9a-z-]+-\d+/[0-9a-z-]+-|[^/]+/\d+/[^/]+/)(?P<id>\d+)'
    _TEST = {
        'url': 'https://www.mtv.fi/sarja/mtv-uutiset-live-33001002003/lahden-pelicans-teki-kovan-ratkaisun-ville-nieminen-pihalle-1181321',
        'info_dict': {
            'id': '1181321',
            'ext': 'mp4',
            'title': 'MTV Uutiset Live',
            'description': 'Päätöksen teki Pelicansin hallitus.',
            'timestamp': 1575116484,
            'upload_date': '20191130',
            'duration': 37.12,
            'view_count': int,
            'categories': list,
        },
        'params': {
            # m3u8 download
            'skip_download': True,
        },
    }
    _API_DOMAIN = 'api.katsomo.fi'
    _PROTOCOLS = ('HLS', 'MPD')
    _GEO_COUNTRIES = ['FI']
