# Core Imports
import os
from urllib import quote
import json

# 3rd Party Imports
import requests

TOKEN = os.getenv('PIVOTAL_TOKEN', None)


def find_project_for_story(story_id):
    """If we have multiple projects, will loop through the projects to find the one with the given story.
    returns None if not found
    """

    for project in Project.all():
        story = project.load_story(story_id)
        if story is not None:
            return project

    #Not found
    print "No project found for story: #{}".format(story_id)
    return None


def get_project_by_index(index):
    return Project.all()[index]


class Note(object):
    """object representation of a Pivotal Note, should be accessed from story.notes"""
    def __init__(self, note_id, text, author):
        self.note_id = note_id
        self.text = text
        self.author = author


class Task(object):
    """object representation of a Pivotal Task, should be accessed from story.tasks"""
    def __init__(self, task_id, description, complete):
        self.task_id = task_id
        self.description = description
        self.complete = complete


class Attachment(object):
    """object representation of a Pivotal attachment, should be accessed from story.attachments"""
    def __init__(self, attachment_id, description, url):
        self.attachment_id = attachment_id
        self.description = description
        self.url = url


class Story(object):
    """object representation of a Pivotal story"""
    def __init__(self):
        self.story_id = None
        self.project_id = None
        self.name = None
        self.description = None
        self.owned_by = None
        self.story_type = None
        self.estimate = None
        self.state = None
        self.url = None
        self.labels = None
        self.notes = []
        self.attachments = []
        self.tasks = []


    @property
    def first_label(self):
        """returns the first label if any from labels.  Used for grouping"""
        if self.labels:
            return self.labels[0]
        else:
            return None


    @classmethod
    def find(cls, story_id, project_index=None):
        project = None
        if project_index is None:
            project = find_project_for_story(story_id)

        else:
            project = Project.all()[project_index]

        if project is not None:
            return project.load_story(story_id)
        else:
            return None



    @classmethod
    def from_json(cls, node):
        """instantiates a Story object from an elementTree node, build child notes and attachment lists"""

        story = Story()
        story.story_id = _parse_int(node, 'id')
        story.name = _parse_text(node, 'name')
        story.owned_by = _parse_text(node, 'owned_by')
        story.story_type = _parse_text(node, 'story_type')
        story.state = _parse_text(node, 'current_state')
        story.description = _parse_text(node, 'description')
        story.estimate = _parse_int(node, 'estimate')
        story.labels = _parse_array(node, 'labels')
        story.url = _parse_text(node, 'url')
        story.project_id = _parse_int(node, 'project_id')

        note_nodes = node.get('notes')
        if note_nodes is not None:
            for note_node in note_nodes:
                note_id = _parse_int(note_node, 'id')
                text = _parse_text(note_node, 'text')
                author = _parse_text(note_node, 'author')
                story.notes.append(Note(note_id, text, author))

        attachment_nodes = node.get('attachments')
        if attachment_nodes is not None:
            for attachment_node in attachment_nodes:
                attachment_id = _parse_int(attachment_node, 'id')
                description = _parse_text(attachment_node, 'text')
                url = _parse_text(attachment_node, 'url')
                story.attachments.append(Attachment(attachment_id,description,url))

        task_nodes = node.get('tasks')
        if task_nodes is not None:
            for task_node in task_nodes:
                task_id = _parse_int(task_node, 'id')
                description = _parse_text(task_node, 'description')
                complete = _parse_boolean(task_node, 'complete')
                story.tasks.append(Task(task_id, description, complete))



        return story

    def assign_estimate(self, estimate):
        """changes the estimate of a story"""
        return self.update(estimate=estimate)

    def update(self, **payload):
        """changes the estimate of a story"""
        update_story_url ="https://www.pivotaltracker.com/services/v5/projects/{}/stories/{}".format(self.project_id, self.story_id)
        return _perform_pivotal_put(update_story_url, payload)

    def set_state(self, state):
        """changes the estimate of a story"""
        return self.update(current_state=state)

    def finish(self):
        if self.estimate == -1:
            raise InvalidStateException('Story must be estimated')
        self.set_state('finished')

    def start(self):
        if self.estimate == -1:
            raise InvalidStateException('Story must be estimated')
        self.set_state('started')

    def deliver(self):
        if self.estimate == -1:
            raise InvalidStateException('Story must be estimated')
        self.set_state('delivered')

    def accept(self):
        self.set_state('accepted')

    def reject(self):
        self.set_state('rejected')


class InvalidStateException(Exception): pass

class Project(object):
    """object representation of a Pivotal Project"""

    def __init__(self, project_id, name, point_scale):
        self.project_id = project_id
        self.name = name
        self.point_scale = point_scale

    @classmethod
    def from_json(cls, project_node):
        name = _parse_text(project_node, 'name')
        id = _parse_int(project_node, 'id')
        point_scale = _parse_array(project_node, 'point_scale')
        return Project(id, name, point_scale)

    @classmethod
    def all(cls):
        """returns all projects for the given user"""
        projects_url = 'https://www.pivotaltracker.com/services/v5/projects'
        root = _perform_pivotal_get(projects_url)
        if root is not None:
            return [Project.from_json(project_node) for project_node in root]

    @classmethod
    def load_project(cls, project_id):
        url = "https://www.pivotaltracker.com/services/v5/projects/%s" % project_id
        response = _perform_pivotal_get(url)
        name = _parse_text(response, 'name')
        return Project(project_id, name)

    def get_stories(self, filter_string):
        """Given a filter strong, returns an list of stories matching that filter.  If none will return an empty list
        Look at [link](https://www.pivotaltracker.com/help/faq#howcanasearchberefined) for syntax

        """

        story_filter = quote(filter_string, safe='')
        stories_url = "https://www.pivotaltracker.com/services/v5/projects/{}/stories?filter={}".format(self.project_id, story_filter)

        response = _perform_pivotal_get(stories_url)
        return [Story.from_json(story_node) for story_node in response]

    def load_story(self, story_id):
        """Trys to find a story, returns None is not found"""
        story_url = "https://www.pivotaltracker.com/services/v5/projects/{}/stories/{}".format(self.project_id, story_id)


        try:
            response = _perform_pivotal_get(story_url)
            return Story.from_json(response)
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                # Not Found
                return None
            raise

    def create_story(self, story_dict):
        stories_url = "https://www.pivotaltracker.com/services/v5/projects/{}/stories".format(self.project_id)
        _perform_pivotal_post(stories_url, story_dict)

    def unestimated_stories(self):
        stories = self.get_stories('type:feature state:unstarted')
        return self.open_bugs() + [story for story in stories if int(story.estimate) == -1]

    def open_bugs(self):
        return self.get_stories('type:bug state:unstarted')

    def in_progress_stories(self):
        return self.get_stories('state:started,rejected')

    def finished_features(self):
        return self.get_stories('state:delivered,finished type:feature')

    def finished_bugs(self):
        return self.get_stories('state:delivered,finished type:bug')

    def known_issues(self):
        return self.get_stories('state:unscheduled,unstarted,started,rejected type:bug')


# TODO Handle requests.exceptions.ConnectionError

def _perform_pivotal_get(url):
    headers = {'X-TrackerToken': TOKEN}
    # print url
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()


def _perform_pivotal_put(url, payload):
    headers = {'X-TrackerToken': TOKEN, 'Content-type': "application/json"}
    response = requests.put(url, headers=headers, data=json.dumps(payload))
    response.raise_for_status()
    return response.json()

def _perform_pivotal_post(url, payload):
    headers = {'X-TrackerToken': TOKEN, 'Content-type': "application/json"}
    response = requests.post(url, data=json.dumps(payload), headers=headers)
    response.raise_for_status()
    return response.json()


def _parse_text(node, key):
    """parses test from an ElementTree node, if not found returns empty string"""
    element = node.get(key)
    if element is not None:
        if element is not None:
            return element.strip()
        else:
            return ''
    else:
        return ''


def _parse_int(node, key):
    """parses an int from an ElementTree node, if not found returns None"""
    element = node.get(key)
    if element is not None:
        return int(element)
    else:
        return None


def _parse_array(node, key):
    """parses an int from an ElementTree node, if not found returns None"""
    element = node.get(key)
    if element is not None:
        return element
    else:
        return None

def _parse_boolean(node, key):
    """parses an boolean from an ElementTree node, if not found returns None"""
    element = node.get(key)
    if element is not None:
        return bool(element)
    else:
        return None
