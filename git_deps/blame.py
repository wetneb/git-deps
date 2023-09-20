import subprocess
import re
from dataclasses import dataclass

# The following classes are introduced to imitate their counterparts in pygit2,
# so that the output of 'blame_via_subprocess' can be swapped with pygit2's own
# blame output.

@dataclass
class GitRef:
    """
    A reference to a commit
    """
    hex: str

@dataclass
class Author:
    """
    Representation of authorship information from a commit
    (only the fields we care about for dependency detection)
    """
    time: int

@dataclass
class BlameHunk:
    """
    A chunk of a blame output which has the same commit information
    for a consecutive set of lines
    """
    orig_commit_id: GitRef
    orig_start_line_number: int
    final_start_line_number: int
    lines_in_hunk: int = 1
    final_committer: Author = None
    orig_committer: Author = None

def blame_via_subprocess(path, commit, start_line, num_lines):
    """
    Generate a list of blame hunks by calling 'git blame' as a separate process.
    This is a workaround for the slowness of pygit2's own blame algorithm.
    See https://github.com/aspiers/git-deps/issues/1
    """
    cmd = [
        'git', 'blame',
        '--porcelain',
        '-L', "%d,+%d" % (start_line, num_lines),
        commit, '--', path
    ]
    output = subprocess.check_output(cmd, universal_newlines=True)

    start_hunk_re = re.compile(r'^([0-9a-f]{40}) (\d+) (\d+) (\d+)$')
    committer_time_re = re.compile(r'^committer-time (\d+)$')
    author_time_re = re.compile(r'^author-time (\d+)$')

    current_hunk = None
    commit_times = {}
    author_times = {}

    def finalize_hunk(hunk):
        commit_time = commit_times.get(hunk.orig_commit_id.hex)
        if commit_time:
            hunk.final_committer = Author(commit_time)
        author_time = author_times.get(hunk.orig_commit_id.hex)
        if author_time:
            hunk.orig_committer = Author(author_time)
        return hunk

    for line in output.split('\n'):
        m = start_hunk_re.match(line)
        if m: # starting a new hunk
            if current_hunk:
                yield finalize_hunk(current_hunk)
            dependency_sha1, orig_line_num, line_num, length = m.group(1, 2, 3, 4)
            orig_line_num = int(orig_line_num)
            line_num = int(line_num)
            length = int(length)
            current_hunk = BlameHunk(
                orig_commit_id=GitRef(dependency_sha1),
                orig_start_line_number = orig_line_num,
                final_start_line_number = line_num,
                lines_in_hunk = length
            )

        m = committer_time_re.match(line)
        if m:
            committer_time = int(m.group(1))
            commit_times[current_hunk.orig_commit_id.hex] = committer_time

        m = author_time_re.match(line)
        if m:
            author_time = int(m.group(1))
            author_times[current_hunk.orig_commit_id.hex] = author_time

    if current_hunk:
        yield finalize_hunk(current_hunk)
