#!/bin/bash

# source branch
source_branch="main"

# target branch
target_branch="extra"

# remote name
remote_name="coding"

# remote branch
remote_branch="main"

# get the current branch
current_branch=$(git branch --show-current)

# path to the temporary file used to prevent re-entry
lock_file="pre-push.lock"

# check if the lock file exists
if [ -f "$lock_file" ]; then
  exit 0
fi

# create the lock file
touch "$lock_file"

# ensure the lock file is removed on exit
# see: https://wangchujiang.com/linux-command/c/trap.html
trap 'rm -f "$lock_file"' EXIT

# only execute if the current branch equals source branch
if [ "$current_branch" = "$source_branch" ]; then
  # perform push operation
  # if ! git push -f origin $source_branch; then
  #   echo "failed to push to origin, exiting"
  #   exit 1
  # fi

  # switch to target branch
  if ! git checkout $target_branch; then
    echo "failed to checkout target branch: $target_branch, exiting"
    exit 1
  fi

  # pull the latest code from the remote repository to ensure target branch is up-to-date
  if ! git pull $remote_name $remote_branch; then
    echo "failed to pull from remote, exiting"
    exit 1
  fi

  # rebase changes from source branch onto target branch
  if ! git rebase $source_branch; then
    echo "failed to rebase, exiting"
    exit 1
  fi
  
  # push the changes of target branch to the remote repository
  if ! git push -f $remote_name $target_branch:$remote_branch; then
    echo "failed to push to branch: $remote_name/$remote_branch, exiting"
    exit 1
  fi

  # print result
  echo "sync changes from branch $source_branch to $remote_name/$remote_branch successed"
  
  # switch back to source branch
  if ! git checkout $source_branch; then
    echo "failed to checkout source branch: $source_branch, exiting"
    exit 1
  fi

  # exit to avoid repeated push
  exit 0
fi

# for other cases, continue with the default push operation
exit 0