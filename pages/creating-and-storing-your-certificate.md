# Creating and storing your certificate

Based off my experiences with StartSSL.

## Requirements
* OpenSSL
* Some patience
* An account with StartSSL.com

## Steps
First we need to create a CSR file and a private key. We use the private key on our server and ship the CSR file to StartSSL.com for signing, thus getting our certificate.

Create the CSR:

```bash
openssl req -out www.here.dk.csr -new -newkey rsa:2048 -nodes -keyout www.here.dk.key`
```

If you haven’t already, it’s time to register with [StartSSL.com](http://www.startssl.com/) and submit the CSR.

While they offer to create the public and private key pairs for you, I recommend against that, as it allows StartSSL and potentially third parties access to your private key and any information encrypted using it.

After creating you account and getting yourself and your request vetted, it’s time to get the signed .crt from them, rename it per your liking, and fetch their intermediate certificate from [Class 1 Intermediate Server CA](https://www.startssl.com/certs/sub.class1.server.ca.pem).

This is all that is required to get the certificate. Installing it should be covered by your system documentation.

I do recommend taking the extra step of creating an encrypted PKCS#12 backup file in case you need to access the certificate again at a later date:

```bash
openssl pkcs12 -export -out www.here.dk.pfx -inkey www.here.dk.key -in www.here.dk.crt -certfile sub.class1.server.ca.pem
```

I now have a .PFX created containing the key, certificate, and intermediate CA, which is immediately digestible by the GUI in OS X, Windows, and OpenSSL itself.

After installing and backing up your certificate, make sure to erase your unencrypted key from anywhere you don’t have proper security in place, as we skipped securing it until we created the backup file.
