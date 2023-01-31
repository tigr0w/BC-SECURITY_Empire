FROM parrotsec/core:latest
WORKDIR /empire
COPY . /empire
RUN yes n | /empire/setup/install.sh
RUN rm -rf /empire/empire/server/data/empire*
RUN yes | ./ps-empire server --reset
ENTRYPOINT ["./ps-empire"]
CMD ["server"]
