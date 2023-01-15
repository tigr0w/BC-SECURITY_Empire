FROM ubuntu:20.04
WORKDIR /empire
COPY . /empire
RUN sed -i 's/use: mysql/use: sqlite/g' empire/server/config.yaml
RUN yes n | /empire/setup/install.sh
RUN rm -rf /empire/empire/server/data/empire*
RUN yes | ./ps-empire server --reset
ENTRYPOINT ["./ps-empire"]
CMD ["server"]
