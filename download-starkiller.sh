# This is a temporary script to download the Starkiller files.
# It's nice for development right now, but we'll probably want to
# productionize it in some way or make it part of release process.
# also not ideal because it requires installing https://github.com/gruntwork-io/fetch
# tried using a bare shell script but it didn't work.

# BEFORE RUNNING YOU MUST RUN export GITHUB_OAUTH_TOKEN=<your token>
# WHERE YOUR TOKEN IS A PERSONAL ACCESS TOKEN
REPO="bc-security/starkiller-sponsors"
VERSION="v2.0.0-alpha1"
FILE="starkiller-dist.tar.gz"

fetch --repo https://github.com/$REPO --tag $VERSION --release-asset $FILE .

rm -rf ./empire/server/v2/api/static/*

# Extract the file
tar -xzf $FILE -C ./empire/server/v2/api/static/

# move data from dist/ to static/
mv ./empire/server/v2/api/static/dist/* ./empire/server/v2/api/static/