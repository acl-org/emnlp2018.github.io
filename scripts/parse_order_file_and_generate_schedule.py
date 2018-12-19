#!/usr/bin/env python3

'''
This script parses the following four files and generates the HTML that can
then be added to the program page on the website:

- order.txt
- authors.csv
- session-chairs.csv [optional]
- anthology-mapping.csv [optional]

Note that:

1. `dos2unix` must be run on the order file before processing.

2. The order file does not contain any information about tutorials, workshops, or welcome reception.

3. It also does not contain any authors for any papers/posters/demos.

4. The first three files were provided by the program chairs.

5. The last file was scraped manually from the anthology webpage. Although this should not be necessary as the anthology links are generated based on the `order.txt` file, in this case, changes were made to the order file AFTER the handbook was published and, therefore, the anthology was out of sync.

6. If the session chairs file is not provided, the schedule and the app will contain "TBD" for all sessions as the chair.

7. If the anthology mapping file is not provided, the PDF icons in the schedule linked to the anthology URL will not be generated.

'''

import argparse
import csv
import logging
import re

from itertools import count, cycle

# define some regular expressions to parse the various order file entries
NON_PAPER_SESSION_REGEXP = re.compile(r'([0-9]{2}:[0-9]{2})--([0-9]{2}:[0-9]{2})\s+(.*?)\s+\((.*?)\)')
BREAK_SESSION_REGEXP = re.compile(r'([0-9]{2}:[0-9]{2})--([0-9]{2}:[0-9]{2})\s+(.*)')
PAPER_SESSION_GROUP_REGEXP = re.compile(r'([0-9]{2}:[0-9]{2})--([0-9]{2}:[0-9]{2})\s+(.*?)\((.*?)\)\s+(.*)')
PAPER_SESSION_REGEXP = re.compile(r'Session ([^:]+): ([^\(]+) \((.*?)\)')
PAPER_REGEXP = re.compile(r'([^ ]+)\s+([0-9]{2}:[0-9]{2})--([0-9]{2}:[0-9]{2})\s#\s(.*)')
POSTER_DEMO_REGEXP = re.compile(r'([^ ]+)\s#\s(.*)')
BEST_PAPER_REGEXP = re.compile(r'([^ ]+)\s+([0-9]{2}:[0-9]{2})--([0-9]{2}:[0-9]{2})\s#\s(.*)')

KEYNOTE_ABSTRACT_DICT = {
    'Julia': 'Detecting deception from various forms of human behavior is a longstanding research goal which is of considerable interest to the military, law enforcement, corporate security, social services and mental health workers. However, both humans and polygraphs are very poor at this task. We describe more accurate methods we have developed to detect deception automatically from spoken language. Our classifiers are trained on the largest cleanly recorded corpus of within-subject deceptive and non-deceptive speech that has been collected. To distinguish truth from lie we make use of acoustic-prosodic, lexical, demographic, and personality features. We further examine differences in deceptive behavior based upon gender, personality, and native language (Mandarin Chinese vs. English), comparing our systems to human performance. We extend our studies to identify cues in trusted speech vs. mistrusted speech and how these features differ by speaker and by listener. Why does a listener believe a lie?',
    'Gideon': 'Since the dawn of human civilization, finance and language technology have been connected. However, only recently have advances in statistical language understanding, and an ever-increasing thirst for market advantage, led to the widespread application of natural language technology across the global capital markets. This talk will review the ways in which language technology is enabling market participants to quickly understand and respond to major world events and breaking business news. It will outline the state of the art in applications of NLP to finance and highlight open problems that are being addressed by emerging research.',
    'Johan': 'There are many recent advances in semantic parsing: we see a rising number of semantically annotated corpora and there is exciting technology (such as neural networks) to be explored. In this talk I will discuss what role computational semantics could play in future natural language processing applications (including fact checking and machine translation). I will argue that we should not just look at semantic parsing, but that things can get really interesting when we can use language-neutral meaning representations to draw (transparent) inferences. The main ideas will be exemplified by the parallel meaning bank, a new corpus comprising texts annotated with formal meaning representations for English, Dutch, German and Italian.'}


def process_line(line):
    end_index = line.find('[') if '[' in line else len(line)
    processed_line = line[:end_index].strip()
    return processed_line


def collect_instances(iterator, character):
    groups = []
    group = []
    start = True
    while 1:
        try:
            line = next(iterator)
        except StopIteration:
            groups.append(group)
            break
        else:
            if line.startswith(character):
                if start:
                    group.append(line)
                    start = False
                else:
                    groups.append(group)
                    group = [line]
            else:
                if not line:
                    continue
                group.append(line)
    return groups


def get_session_chair_link(chairs_dict, session_id):
    if chairs_dict:
        session_chair_name, session_chair_email = chairs_dict[session_id]
        ans = '<a href="mailto:{}">{}</a>'.format(session_chair_name, session_chair_email)
    else:
        ans = 'TBD'
    return ans


def get_anthology_link(anthology_dict, paper_title):
    if anthology_dict:
        anthology_id = anthology_dict[paper_title.lower()]
        anthology_url = "http://aclweb.org/anthology/{}".format(anthology_id)
        ans = '&nbsp;&nbsp;<i class="fa fa-file-pdf-o paper-icon" data="{}" aria-hidden="true"></i>'.format(anthology_url)
    else:
        ans = ''
    return ans


def main():

    # set up an argument parser
    parser = argparse.ArgumentParser(prog='parse_order_file_and_generate_schedule.py')
    parser.add_argument("--order",
                        dest="order_file",
                        required=True,
                        help="Path to order file containing session information")
    parser.add_argument("--authors",
                        dest="authors_csv",
                        required=True,
                        help="Path to CSV file containing author information")
    parser.add_argument("--chairs",
                        dest="chairs_csv",
                        required=False,
                        default=None,
                        help="Path to optional CSV file containing session chair information")
    parser.add_argument("--anthology",
                        dest="anthology_csv",
                        required=False,
                        default=None,
                        help="Path to optional CSV file containing anthology IDs for papers, posters, and demos")

    # parse given command line arguments
    args = parser.parse_args()

    # set up the logging
    logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.INFO)

    # initialize the list of generated HTML items
    generated_html = []

    # open order file and capture the contents of each day into separate lists
    with open(args.order_file, 'r') as orderfh:
        processed_lines = [process_line(line) for line in orderfh]
    days = collect_instances(iter(processed_lines), '*')

    # read in the CSV file mapping paper IDs to authors
    authors_dict = {}
    with open(args.authors_csv, 'r') as authorsfh:
        reader = csv.DictReader(authorsfh, fieldnames=["Submission ID", "Authors"])
        for row in reader:
            assert row['Submission ID'] not in authors_dict
            authors_dict[row['Submission ID']] = row['Authors']

    # read in the CSV file mapping sessions to chairs
    chairs_dict = {} 
    if args.chairs_csv:
        with open(args.chairs_csv, 'r') as chairsfh:
            reader = csv.DictReader(chairsfh, fieldnames=["Session", "Name", "Email"])
            for row in reader:
                session_id = row['Session'].split(':')[0]
                assert session_id not in chairs_dict
                chairs_dict[session_id] = (row['Name'], row['Email'])

    # read in the CSV file mapping paper/poster titles to anthology IDs
    anthology_dict = {}
    if args.anthology_csv:
        with open(args.anthology_csv, 'r') as anthologyfh:
            reader = csv.DictReader(anthologyfh, fieldnames=["Title", "ID"])
            for row in reader:
                anthology_dict[row['Title'].lower()] = row['ID']

    # now in each day, process each session one by one
    days_counter = count(start=3)
    lunch_id_counter = count(start=3)
    break_id_counter = count(start=1)
    paper_session_group_counter = count(start=1)
    paper_session_counter = cycle([1, 2, 3, 4])
    poster_session_counter = count(start=1)
    for day in days:
        day_string = day.pop(0).lstrip('* ')
        generated_html.append('<div class="day" id="day-{}">{}</div>'.format(next(days_counter), day_string))

        # take the days's contents and group them into sessions
        day_sessions = collect_instances(iter(day), '+')

        # now iterate over each session in the day
        for session in day_sessions:
            session_string = session.pop(0).lstrip('+ ').strip()
            if 'break' in session_string.lower() or 'lunch' in session_string.lower():
                session_start, session_end, break_title = BREAK_SESSION_REGEXP.match(session_string).groups()
                if break_title.lower() == 'lunch':
                    break_title = 'Lunch'
                    break_type = 'lunch'
                    break_id = next(lunch_id_counter)
                elif 'mini' in break_title.lower():
                    break_title = 'Mini-Break'
                    break_type = 'break'
                    break_id = next(break_id_counter)
                else:
                    break_title = 'Coffee Break'
                    break_type = 'break'
                    break_id = next(break_id_counter)
                generated_html.append('<div class="session session-break session-plenary" id="session-{}-{}"><span class="session-title">{}</span><br/><span class="session-time" title="{}">{} &ndash; {}</span></div>'.format(break_type, break_id, break_title, day_string, session_start, session_end))
            elif 'keynote' in session_string.lower():
                session_start, session_end, session_title, session_location = NON_PAPER_SESSION_REGEXP.match(session_string).groups()
                if 'Julia' in session_title:
                    session_title = session_title.replace('Julia Hirschberg ', '')
                    session_abstract = KEYNOTE_ABSTRACT_DICT['Julia']
                    session_people = 'Julia Hirschberg (Columbia University)'
                    session_people_link = 'http://www.cs.columbia.edu/~julia/'
                elif 'Gideon' in session_title:
                    session_title = session_title.replace('Gideon Mann ', '')
                    session_abstract = KEYNOTE_ABSTRACT_DICT['Gideon']
                    session_people = 'Gideon Mann (Bloomberg, L.P.)'
                    session_people_link = 'https://sites.google.com/site/gideonmann/'
                elif 'Johan' in session_title:
                    session_title = session_title.replace('Johan Bos ', '')
                    session_abstract = KEYNOTE_ABSTRACT_DICT['Johan']
                    session_people = 'Johan Bos (University of Groningen)'
                    session_people_link = 'https://www.rug.nl/staff/johan.bos/'
                generated_html.append('<div class="session session-expandable session-plenary"><div id="expander"></div><a href="#" class="session-title"><strong>{}</strong></a><br/><span class="session-people"><a href="{}" target="_blank">{}</a></span><br/><span class="session-time" title="{}">{} &ndash; {}</span><br/><span class="session-location btn btn--info btn--location">{}</span><div class="paper-session-details"><br/><div class="session-abstract"><p>{}</p></div></div></div>'.format(session_title, session_people_link, session_people, day_string, session_start, session_end, session_location, session_abstract))
            elif 'opening' in session_string.lower():
                session_start, session_end, session_title, session_location = NON_PAPER_SESSION_REGEXP.match(session_string).groups()
                generated_html.append('<div class="session session-plenary" id="session-welcome"><span class="session-title">{}</span><br/><span class="session-time" title="{}">{} &ndash; {}</span><br/> <span class="session-location btn btn--info btn--location">{}</span></div>'.format(session_title, day_string, session_start, session_end, session_location))
            elif 'social event' in session_string.lower():
                session_start, session_end, session_title, session_location = NON_PAPER_SESSION_REGEXP.match(session_string).groups()
                generated_html.append('<div class="session session-expandable session-plenary" id="session-social"><div id="expander"></div><a href="#" class="session-title">{}</a><br/><span class="session-time" title="{}">{} &ndash; {}</span><br/><span class="session-external-location btn btn--info btn--location">{}</span> <div class="paper-session-details"> <br/><div class="session-abstract"><p>On the evening of Saturday, November 3rd, the EMNLP 2018 social event will take place at the Royal Museums of Fine Arts of Belgium. Four museums, housed in a single building, will welcome the EMNLP delegates with their prestigious collection of 20,000 works of art. The Museums’ collections trace the history of the visual arts — painting, sculpture and drawing — from the 15th to the 21st century.</p></div></div></div>'.format(session_title, day_string, session_start, session_end, session_location))
            elif 'business meeting' in session_string.lower():
                session_start, session_end, session_title, session_location = NON_PAPER_SESSION_REGEXP.match(session_string).groups()
                generated_html.append('<div class="session session-expandable session-plenary" id="session-business"><div id="expander"></div><a href="#" class="session-title">{}</a><br/><span class="session-time" title="{}">{} &ndash; {}</span><br/><span class="session-location btn btn--info btn--location">{}</span><br/><div class="paper-session-details"> <br/><div class="session-abstract">All attendees are encouraged to participate in the business meeting.</div></div></div>'.format(session_title, day_string, session_start, session_end, session_location))
            elif 'best paper' in session_string.lower():
                session_start, session_end, session_title, session_location = NON_PAPER_SESSION_REGEXP.match(session_string).groups()
                generated_html.append('<div class="session session-expandable session-papers-best"><div id="expander"></div><a href="#" class="session-title">{}</a><br/><span class="session-time" title="{}">{} &ndash; {}</span><br/><span class="session-location btn btn--info btn--location">{}</span><br/><div class="paper-session-details"><br/><table class="paper-table">'.format(session_title, day_string, session_start, session_end, session_location))
                for paper in session:
                    best_paper_id, best_paper_start, best_paper_end, best_paper_title = BEST_PAPER_REGEXP.match(paper.strip()).groups()
                    best_paper_authors = authors_dict[best_paper_id].strip()
                    best_paper_url = get_anthology_link(anthology_dict, best_paper_title.lower())
                    generated_html.append('<tr id="best-paper" paper-id="{}"><td id="paper-time">{}&ndash;{}</td><td><span class="paper-title">{}. </span><em>{}</em>{}</td></tr>'.format(best_paper_id, best_paper_start, best_paper_end, best_paper_title, best_paper_authors, best_paper_url))
                generated_html.append('</table></div></div>')
            elif 'orals' in session_string.lower():
                session_group_start, session_group_end, session_group_type, session_group_description, session_group_roman_numeral = PAPER_SESSION_GROUP_REGEXP.match(session_string).groups()
                paper_session_group_id = next(paper_session_group_counter)
                session_group_type = session_group_type.replace('and', '&amp;')
                session_group_description = session_group_description.replace('and', '&amp;')
                generated_html.append('<div class="session-box" id="session-box-{}"><div class="session-header" id="session-header-{}">{}{} ({})</div>'.format(paper_session_group_id, paper_session_group_id, session_group_type, session_group_roman_numeral, session_group_description))
                day_session_splits = collect_instances(iter(session), '=')
                for split in day_session_splits:
                    split_string = split.pop(0).lstrip('= ').strip()
                    session_id, session_title, session_parens = PAPER_SESSION_REGEXP.match(split_string).groups()
                    session_title = session_title.replace('and', '&amp;')
                    if ',' in session_parens:
                        session_type, session_location = session_parens.split(', ')
                        session_type = session_type.strip()
                        session_location = session_location.strip()
                    else:
                        session_location = session_parens.strip()
                        session_type = ''
                    if 'poster' in session_type.lower() or 'poster' in session_title.lower():
                        session_title = '{} ({})'.format(session_title, session_type) if session_type else session_title
                        generated_html.append('<div class="session session-expandable session-posters" id="session-poster-{}"><div id="expander"></div><a href="#" class="session-title">{}: {} </a><br/><span class="session-time" title="{}">{} &ndash; {}</span><br/><span class="session-location btn btn--info btn--location">{}</span><div class="poster-session-details"><br/><table class="poster-table">'.format(next(poster_session_counter), session_id, session_title, day_string, session_group_start, session_group_end, session_location))
                    else:
                        session_chair_link = get_session_chair_link(chairs_dict, session_id)
                        generated_html.append('<div class="session session-expandable session-papers{}" id="session-{}"><div id="expander"></div><a href="#" class="session-title">{}: {}</a><br/><span class="session-time" title="{}">{} &ndash; {}</span><br/><span class="session-location btn btn--info btn--location">{}</span><br/><div class="paper-session-details"><br/><a href="#" class="session-selector" id="session-{}-selector"> Choose All</a><a href="#" class="session-deselector" id="session-{}-deselector">Remove All</a><table class="paper-table"><tr><td class="session-chair" colspan="2">Chair: {}</td></tr>'.format(next(paper_session_counter), session_id.lower(), session_id, session_title, day_string, session_group_start, session_group_end, session_location, session_id.lower(), session_id.lower(), session_chair_link))
                    for paper in split:
                        paper = paper.strip()
                        if 'poster' in session_type.lower() or 'poster' in session_title.lower():
                            if paper.startswith('@'):
                                poster_topic = paper.lstrip('@ ')
                                generated_html.append('<tr><td><span class="poster-type">{}</span></td></tr>'.format(poster_topic))
                                continue
                            else:
                                poster_id, poster_title = POSTER_DEMO_REGEXP.match(paper).groups()
                                if poster_id.endswith('-TACL'):
                                    poster_title = '[TACL] {}'.format(poster_title)
                                    # tacl_article_id = poster_id.split('-')[0]
                                    # poster_url = 'https://transacl.org/ojs/index.php/tacl/article/view/{}'.format(tacl_article_id)
                                    poster_url = ''
                                else:
                                    poster_url = get_anthology_link(anthology_dict, poster_title.lower())
                                poster_authors = authors_dict[poster_id].strip()
                                generated_html.append('<tr id="poster" poster-id="{}"><td><span class="poster-title">{}. </span><em>{}</em>{}</td></tr>'.format(poster_id, poster_title, poster_authors, poster_url))
                        else:
                            paper_id, paper_start, paper_end, paper_title = PAPER_REGEXP.match(paper.strip()).groups()
                            paper_authors = authors_dict[paper_id].strip()
                            if paper_id.endswith('-TACL'):
                                paper_title = '[TACL] {}'.format(paper_title)
                                # tacl_article_id = paper_id.split('-')[0]
                                # paper_url = 'https://transacl.org/ojs/index.php/tacl/article/view/{}'.format(tacl_article_id)
                                paper_url = ''
                            else:
                                paper_url = get_anthology_link(anthology_dict, paper_title.lower())
                            generated_html.append('<tr id="paper" paper-id="{}"><td id="paper-time">{}&ndash;{}</td><td><span class="paper-title">{}. </span><em>{}</em>{}</td></tr>'.format(paper_id, paper_start, paper_end, paper_title, paper_authors, paper_url))
                    generated_html.append('</table></div></div>'.format(paper_id, paper_start, paper_end, paper_title))
                generated_html.append('</div>')

    print('\n'.join(generated_html))


if __name__ == '__main__':
    main()
