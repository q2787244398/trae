// TraeCreds - capture the Trae iOS (com.stone.solo.cn) login credentials
// so they can be pasted into the relay console's manual "add account" form.
//
// Scope: only requests whose host is a Trae host are inspected. Nothing is
// uploaded anywhere unless you set kRelayBaseURL below. For your own device
// and your own account only.

#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#import <Security/Security.h>

// Optional: POST captured credentials to your relay. Leave empty to disable.
static NSString *const kRelayBaseURL = @"";

static NSString *const kCredsFile = @"trae-creds.json";

#pragma mark - helpers

static BOOL TraeHost(NSString *url) {
    if (url.length == 0) return NO;
    NSString *l = url.lowercaseString;
    return [l containsString:@"trae.cn"] ||
           [l containsString:@"trae-api-cn"] ||
           [l containsString:@"mchost.guru"];
}

static NSDictionary *DecodeJWT(NSString *jwt) {
    NSArray *parts = [jwt componentsSeparatedByString:@"."];
    if (parts.count < 2) return nil;
    NSString *p = parts[1];
    p = [p stringByReplacingOccurrencesOfString:@"-" withString:@"+"];
    p = [p stringByReplacingOccurrencesOfString:@"_" withString:@"/"];
    while (p.length % 4) p = [p stringByAppendingString:@"="];
    NSData *d = [[NSData alloc] initWithBase64EncodedString:p options:0];
    if (!d) return nil;
    return [NSJSONSerialization JSONObjectWithData:d options:0 error:nil];
}

static NSString *DocsPath(void) {
    NSString *dir = NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
    return [dir stringByAppendingPathComponent:kCredsFile];
}

#pragma mark - store

@interface TraeCredStore : NSObject
@property (nonatomic, copy) NSString *token;
@property (nonatomic, copy) NSString *refreshToken;
@property (nonatomic, copy) NSString *userId;
@property (nonatomic, copy) NSString *clientId;
@property (nonatomic, copy) NSString *lastURL;
+ (instancetype)shared;
- (void)noteRequest:(NSURLRequest *)request;
- (void)noteResponse:(NSData *)data forURL:(NSString *)url;
- (void)flushIfChanged;
@end

@implementation TraeCredStore

+ (instancetype)shared {
    static TraeCredStore *s;
    static dispatch_once_t once;
    dispatch_once(&once, ^{ s = [TraeCredStore new]; s.clientId = @"ono9krqynydwx5"; });
    return s;
}

- (void)noteRequest:(NSURLRequest *)request {
    NSString *url = request.URL.absoluteString ?: @"";
    NSString *auth = [request valueForHTTPHeaderField:@"Authorization"];
    NSString *cloudide = [request valueForHTTPHeaderField:@"X-Cloudide-Token"];
    NSString *cookie = [request valueForHTTPHeaderField:@"Cookie"];
    NSString *jwt = nil;

    if ([auth containsString:@"Cloud-IDE-JWT"]) {
        jwt = [[auth componentsSeparatedByString:@" "] lastObject];
    } else if (auth.length > 20 && [auth hasPrefix:@"eyJ"]) {
        jwt = auth;
    } else if (cloudide.length > 20) {
        jwt = cloudide;
    }
    if (jwt.length < 20) return;

    @synchronized (self) {
        self.lastURL = url;
        if (![jwt isEqualToString:self.token]) {
            self.token = jwt;
            NSDictionary *payload = DecodeJWT(jwt);
            NSDictionary *data = payload[@"data"];
            if ([data isKindOfClass:NSDictionary.class]) {
                id uid = data[@"id"] ?: data[@"uid"];
                if (uid) self.userId = [uid description];
            }
            [self flushIfChanged];
        }
    }

    // A cookie-only session still carries the account id in some builds.
    if (cookie.length && !self.userId) {
        for (NSString *part in [cookie componentsSeparatedByString:@";"]) {
            if ([part.lowercaseString containsString:@"uid"]) {
                NSArray *kv = [part componentsSeparatedByString:@"="];
                if (kv.count == 2) { self.userId = [kv[1] stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceCharacterSet]; }
            }
        }
    }
}

- (void)noteResponse:(NSData *)data forURL:(NSString *)url {
    if (data.length == 0 || data.length > 2 * 1024 * 1024) return;
    NSString *l = url.lowercaseString;
    if (!([l containsString:@"token"] || [l containsString:@"auth"] ||
          [l containsString:@"login"] || [l containsString:@"session"])) return;

    id obj = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
    if (![obj isKindOfClass:NSDictionary.class]) return;

    NSMutableArray *stack = [NSMutableArray arrayWithObject:obj];
    while (stack.count) {
        id cur = stack.lastObject;
        [stack removeLastObject];
        if ([cur isKindOfClass:NSDictionary.class]) {
            for (id k in cur) {
                id v = cur[k];
                NSString *key = [k description].lowercaseString;
                if ([v isKindOfClass:NSString.class] && [v length] > 16) {
                    if ([key isEqualToString:@"refreshtoken"] || [key isEqualToString:@"refresh_token"]) {
                        self.refreshToken = v;
                    } else if (([key isEqualToString:@"token"] || [key isEqualToString:@"accesstoken"] ||
                                [key isEqualToString:@"cloudidetoken"]) && [v hasPrefix:@"eyJ"]) {
                        if (!self.token) self.token = v;
                    } else if ([key isEqualToString:@"userid"] || [key isEqualToString:@"uid"]) {
                        if (!self.userId) self.userId = v;
                    } else if ([key isEqualToString:@"clientid"] || [key isEqualToString:@"client_id"]) {
                        self.clientId = v;
                    }
                } else if ([v isKindOfClass:NSDictionary.class] || [v isKindOfClass:NSArray.class]) {
                    [stack addObject:v];
                }
            }
        } else if ([cur isKindOfClass:NSArray.class]) {
            [stack addObjectsFromArray:cur];
        }
    }
    [self flushIfChanged];
}

- (NSDictionary *)snapshot {
    @synchronized (self) {
        if (self.token.length < 20) return nil;
        return @{ @"token": self.token ?: @"",
                  @"refreshToken": self.refreshToken ?: @"",
                  @"userId": self.userId ?: @"",
                  @"clientId": self.clientId ?: @"ono9krqynydwx5",
                  @"source": self.lastURL ?: @"" };
    }
}

- (void)flushIfChanged {
    NSDictionary *snap = [self snapshot];
    if (!snap) return;

    static NSString *lastJSON = nil;
    NSData *json = [NSJSONSerialization dataWithJSONObject:snap options:NSJSONWritingPrettyPrinted error:nil];
    NSString *text = [[NSString alloc] initWithData:json encoding:NSUTF8StringEncoding];
    if ([text isEqualToString:lastJSON]) return;
    lastJSON = text;

    [text writeToFile:DocsPath() atomically:YES encoding:NSUTF8StringEncoding error:nil];
    UIPasteboard.generalPasteboard.string = text;

    dispatch_async(dispatch_get_main_queue(), ^{
        UIWindow *win = UIApplication.sharedApplication.windows.firstObject;
        UIViewController *top = win.rootViewController;
        while (top.presentedViewController) top = top.presentedViewController;
        if (!top) return;
        UIAlertController *ac = [UIAlertController alertControllerWithTitle:@"Trae 凭据已捕获"
                                                                   message:[NSString stringWithFormat:@"userId: %@\n已复制到剪贴板，可直接粘贴到 relay 控制台。", snap[@"userId"] ?: @"?"]
                                                            preferredStyle:UIAlertControllerStyleAlert];
        [ac addAction:[UIAlertAction actionWithTitle:@"好" style:UIAlertActionStyleDefault handler:nil]];
        [top presentViewController:ac animated:YES completion:nil];
    });

    if (kRelayBaseURL.length) {
        NSMutableURLRequest *req = [NSMutableURLRequest requestWithURL:
            [NSURL URLWithString:[kRelayBaseURL stringByAppendingString:@"/api/web-auth"]]];
        req.HTTPMethod = @"POST";
        [req setValue:@"application/json" forHTTPHeaderField:@"Content-Type"];
        req.HTTPBody = json;
        [[NSURLSession.sharedSession dataTaskWithRequest:req] resume];
    }
}

@end

#pragma mark - hooks

%hook NSURLSession

- (NSURLSessionDataTask *)dataTaskWithRequest:(NSURLRequest *)request
                            completionHandler:(void (^)(NSData *, NSURLResponse *, NSError *))handler {
    NSString *url = request.URL.absoluteString;
    if (TraeHost(url)) {
        @try { [[TraeCredStore shared] noteRequest:request]; } @catch (NSException *e) {}
        if (handler) {
            void (^wrapped)(NSData *, NSURLResponse *, NSError *) = ^(NSData *data, NSURLResponse *resp, NSError *err) {
                @try { [[TraeCredStore shared] noteResponse:data forURL:url]; } @catch (NSException *e) {}
                handler(data, resp, err);
            };
            return %orig(request, wrapped);
        }
    }
    return %orig;
}

%end

%hook NSMutableURLRequest

- (void)setValue:(NSString *)value forHTTPHeaderField:(NSString *)field {
    %orig;
    @try {
        if (TraeHost(self.URL.absoluteString) &&
            ([field.lowercaseString isEqualToString:@"authorization"] ||
             [field.lowercaseString isEqualToString:@"x-cloudide-token"])) {
            [[TraeCredStore shared] noteRequest:self];
        }
    } @catch (NSException *e) {}
}

%end

%hookf(OSStatus, SecItemAdd, CFDictionaryRef attributes, CFTypeRef *result) {
    OSStatus status = %orig;
    @try {
        NSDictionary *dict = (__bridge NSDictionary *)attributes;
        NSString *svc = dict[(__bridge id)kSecAttrService];
        NSString *acct = dict[(__bridge id)kSecAttrAccount];
        if ([svc.lowercaseString containsString:@"trae"] || [svc.lowercaseString containsString:@"solo"] ||
            [acct.lowercaseString containsString:@"trae"]) {
            NSLog(@"[TraeCreds] keychain add svc=%@ acct=%@", svc, acct);
        }
    } @catch (NSException *e) {}
    return status;
}
