#!/usr/bin/env python3
#
# get the list of svg images from a repo
#

import argparse
import datetime
import json
import os
import pathlib
import re
import sh
import shutil
import sys
import time
import yaml

# this assumes that this program is running from the bin directory in the repo
repo_dir = os.path.split(os.path.dirname(os.path.realpath(__file__)))[0]

default_branch = "master"

parser = argparse.ArgumentParser()
parser.add_argument("-q", "--quiet", help="hide status messages", default=True, dest='verbose', action="store_false")
parser.add_argument("--always", help="always process", default=False, dest='always', action="store_true")
parser.add_argument("--branch", help="git branch (default='%s')" % default_branch, action="store", default=default_branch)
parser.add_argument("--cache", help="location of previously downloaded repo", action="store", default=os.path.join(repo_dir, "cache"))
parser.add_argument("--input", help="YAML of potential repos", action="store", default=os.path.join(repo_dir, "docs", "_data", "iconrepos.yaml"))
parser.add_argument("--index", help="index file", action="store", default=os.path.join(repo_dir, "docs", "icons", "searchindex.json"))
parser.add_argument("--output", help="output directory", action="store", default=os.path.join(repo_dir, "docs", "icons"))
parser.add_argument('repos', help='repo ids (all if none specified)', metavar='repos', nargs='*')

args = parser.parse_args()

if args.verbose:
	sys.stdout.write("INFO: updateindex starting at %s\n" % datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'))

if args.verbose:
	sys.stdout.write("INFO: loading repo list from %s\n" % (args.input))
fdata = open(args.input, "r")
rawdata = yaml.load(fdata)
fdata.close()

repolist = {}
for data in rawdata:
	repolist[data['id']] = data
if args.verbose:
	sys.stdout.write("INFO: %d repos listed\n" % (len(rawdata)))

if len(args.repos) == 0:
	args.repos = sorted(repolist.keys())

if args.verbose:
	sys.stdout.write("INFO: will process %d repo(s)\n" % (len(args.repos)))

if os.path.isfile(args.index):
	data = json.load(open(args.index))
else:
	if args.verbose:
		sys.stdout.write("INFO: creating new index\n")
	data = []

total = 0
origdir = os.getcwd()
cachedir = os.path.abspath(args.cache)
outputdir = os.path.abspath(args.output)

pathlib.Path(cachedir).mkdir(parents=True, exist_ok=True)

for repo_id in args.repos:

	if repo_id not in repolist:
		print("ERROR: no repo in list with id '%s'" % (repo_id))
		sys.exit(1)

	repodata = repolist[repo_id]

	sys.stdout.write("OUTPUT: processing %s (%s)\n" % (repo_id, repodata["repo"]))

	gitdir = os.path.join(cachedir, repo_id)
	if args.verbose:
		print("INFO: git repo directory %s" % gitdir)

	giturl = "https://github.com/" + repodata['repo']

	if os.path.isdir(gitdir):
		os.chdir(gitdir)

		cached_commit = sh.git("rev-parse", "HEAD")

		if args.verbose:
			print("INFO: local repo found! pulling changes from git repo %s" % giturl)
		sh.git.pull(_err_to_out=True, _out=os.path.join(cachedir, "git-" + repo_id + ".stdout"))
		if args.verbose:
			print("INFO: pull complete")

		current_commit = sh.git("rev-parse", "HEAD")
		if cached_commit == current_commit:
			if args.always:
				print("INFO: no changes to repo since last run but processing anyway")
			else:
				print("INFO: no changes to repo since last run")
				continue
	else:
		if args.verbose:
			print("INFO: cloning git repo %s" % giturl)
		sh.git.clone(giturl, gitdir, _err_to_out=True, _out=os.path.join(cachedir, "git-" + repo_id + ".stdout"))
		if args.verbose:
			print("INFO: clone complete")
		os.chdir(gitdir)

	if args.verbose:
		print("INFO: switching to branch '%s'" % (repodata['branch']))
	sh.git.checkout(repodata['branch'], _err_to_out=True, _out=os.path.join(cachedir, "git-" + repo_id + ".stdout"))

	logodir = os.path.join(gitdir, repodata['directory'])
	if args.verbose:
		print("INFO: loading svgs from %s" % logodir)
	svgs = []
	pathfix = re.compile(repodata["rename"]) if "rename" in repodata else None

	for srcpath in pathlib.Path(logodir).glob("**/*.svg"):

		shortpath = os.path.join('repos', repo_id, str(srcpath)[len(logodir)+1:] if len(repodata["directory"]) > 0 else str(srcpath)[len(logodir):])

		if pathfix is not None:
			fixdir, fixname = os.path.split(shortpath)
			fixname = pathfix.sub("\\1", fixname)
			shortpath = os.path.join(fixdir, fixname)

		dstpath = os.path.join(outputdir, shortpath)

		if (pathlib.Path(dstpath).exists()):
			continue

		dstdir, dstname = os.path.split(dstpath)

		pathlib.Path(dstdir).mkdir(parents=True, exist_ok=True)
		os.symlink(str(srcpath), dstpath)

		sys.stdout.write("symlink from '%s' to '%s' %s %s\n" % (str(srcpath), dstpath, repo_id, shortpath))

		svgs.append({
			'name': os.path.splitext(dstname)[0],
			'src': giturl + "/blob/" + repodata['branch'] + str(srcpath)[len(gitdir):],
			'img': shortpath
			})


	print("OUTPUT: %d svg files found for %s (%s)" % (len(svgs), repo_id, repodata['repo']))
	total += len(svgs)

	if len(svgs) == 0:
		continue

	#data.extend(svgs[0:2])
	data.extend(svgs)

os.chdir(origdir)

# WTF?  why isn't there an easy way to unique sort dicts???
data = map(lambda svg: frozenset(svg.items()), data)
data = sorted(set(data), key=lambda svg: dict(svg)['img'])
data = list(map(lambda svg: dict(svg), data))

with open(args.index, 'w') as outfile:
	json.dump(data, outfile, sort_keys=True, indent=2)

if args.verbose:
	sys.stdout.write("INFO: updateindex complete: %d logos processed at %s (%d total)\n" % (total, datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'), len(data)))
