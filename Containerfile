# Use an official Python runtime as a parent image
FROM python:3.12

# Set the working directory to /app
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Build TA-lib
RUN wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz \
  && tar -xzf ta-lib-0.4.0-src.tar.gz \
  && rm ta-lib-0.4.0-src.tar.gz \
  && cd ta-lib/ \
  && ./configure --prefix=/usr \
  && make \
  && make install \
  && cd ~ \
  && rm -rf ta-lib/
  
# Install any needed packages specified in requirements.txt
RUN pip install -r requirements.txt

# Run main.py when the container launches
CMD ["python", "src/main.py"]

