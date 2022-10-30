FROM debian:buster
WORKDIR /empire
COPY . /empire
RUN echo 'n\nn\nn\ny\n' | /empire/setup/install.sh
RUN rm -rf /empire/empire/server/data/empire*
RUN yes | ./ps-empire server --reset
ENTRYPOINT ["./ps-empire"]
CMD ["server"]
