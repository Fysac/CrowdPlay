#!/usr/bin/env python

import json
import spotipy
import time
from slackclient import SlackClient
from spotipy import util
from threading import Thread

config = {}
with open('config.json') as f:
    config = json.loads(f.read())

SLACK_TOKEN = config['slack_token']
SPOTIFY_USERNAME = config['spotify_username']
SPOTIFY_CLIENT_ID = config['spotify_client_id']
SPOTIFY_CLIENT_SECRET = config['spotify_client_secret']
SPOTIFY_PLAYLIST_ID = config['spotify_playlist_id']
SPOTIFY_SCOPE = config['spotify_scope']
ALLOW_EXPLICIT = config['allow_explicit']

token = spotipy.util.prompt_for_user_token(
        username=SPOTIFY_USERNAME,
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
        redirect_uri='http://localhost',
        scope=SPOTIFY_SCOPE)

sp = spotipy.Spotify(auth=token)

add_requests = {}

def get_currently_playing():
    results = sp.currently_playing()
    return results['item']['id']

def find_tracks(q):
    results = sp.search(q=q, limit=10)
    return results['tracks']['items']

def add_track(track):
    sp.user_playlist_add_tracks(SPOTIFY_USERNAME, SPOTIFY_PLAYLIST_ID, [track['id']])

def remove_track(id):
    sp.user_playlist_remove_all_occurrences_of_tracks(SPOTIFY_USERNAME, SPOTIFY_PLAYLIST_ID, tracks=[id])

def delete_up_to_curr_track():
    curr_play = get_currently_playing()
    results = sp.user_playlist(user=SPOTIFY_USERNAME, playlist_id=SPOTIFY_PLAYLIST_ID)
    for r in results['tracks']['items']:
        if curr_play == r['track']['id']:
            break
        remove_track(r['track']['id'])

def process_dm(m, tracks, track_entries):
    channel = m['channel']
    channel_info = sc.api_call('conversations.info', channel=channel)
    
    if channel_info['ok']:
        if channel_info['channel']['is_im']:
            try:
                tracks.extend(find_tracks(m['text']))
            except Exception as e:
                print str(e)
                sc.api_call('chat.postMessage', channel=channel, text='Sorry, an error occurred.')
                return
            
            if not ALLOW_EXPLICIT:
                tracks[:] = [t for t in tracks if not t['explicit']]

            for i in range(len(tracks)):
                artists = []
                for a in tracks[i]['artists']:
                    artists.append(a['name'])
                
                track_entries.append('*' + chr(ord('A') + i) + ')* ' + '/'.join(artists) + ' - ' + tracks[i]['name'])

            if len(tracks) > 0:
                sc.api_call('chat.postMessage', channel=channel,
                    text='We found the following tracks matching *' + m['text'] + '*:\n' + '\n'.join(track_entries) + '\n\nPlease make a selection or type *cancel*.')
            else:
                sc.api_call('chat.postMessage', channel=channel, text='No tracks found.')
                add_requests.pop(m['user'], None)

def read_slack(sc):
    if sc.rtm_connect():
        print 'Connected to Slack.'

        my_id = sc.api_call('auth.test')['user_id']

        while sc.server.connected:
            for m in sc.rtm_read():
                if m['type'] == 'message' and 'user' in m and m['user'] != my_id:
                    if m['user'] in add_requests:
                        channel = add_requests[m['user']][0]['channel']

                        selection = m['text'].lower()

                        if selection == 'cancel':
                            sc.api_call('chat.postMessage', channel=channel, text='Request canceled.')
                            add_requests.pop(m['user'], None)
                            continue

                        try:
                            selection = ord(selection) - ord('a')
                        except Exception as e:
                            sc.api_call('chat.postMessage', channel=channel, text='Invalid selection.')
                            continue
                        
                        tracks = add_requests[m['user']][1]
                        if selection >= len(tracks) or selection < 0:
                             sc.api_call('chat.postMessage', channel=channel, text='Invalid selection.')
                             continue
                        
                        try:
                            add_track(tracks[selection])
                            sc.api_call('chat.postMessage', channel=channel, text='Added track ' + add_requests[m['user']][2][selection])
                        except Exception as e:
                            print str(e)
                            sc.api_call('chat.postMessage', channel=channel, text='Sorry, an error occurred.')

                        add_requests.pop(m['user'], None)

                        try:
                            delete_up_to_curr_track()
                        except Exception as e:
                            print str(e)

                    else:
                        tracks = []
                        track_entries = []

                        add_requests[m['user']] = (m, tracks, track_entries)
                        t = Thread(target=process_dm, args=(m, tracks, track_entries))
                        t.start()

if __name__ == '__main__':
    sc = SlackClient(SLACK_TOKEN)
    read_slack(sc)
