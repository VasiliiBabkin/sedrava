#define _GNU_SOURCE
#include <sys/types.h>
#include <sys/wait.h>
#include <sys/resource.h>
#include <sys/time.h>
#include <time.h>
#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <fcntl.h>
int main(int argc,char **argv){
  if(argc<2)return 2;
  struct timespec start,end;
  struct rusage ru;
  int null=open("/dev/null",O_WRONLY);
  if(null<0)return 3;
  clock_gettime(CLOCK_MONOTONIC,&start);
  pid_t child=fork();
  if(child<0)return 4;
  if(child==0){
    if(dup2(null,1)<0 || dup2(null,2)<0)_exit(125);
    close(null);execv(argv[1],argv+1);_exit(126);
  }
  close(null);
  int status;
  if(wait4(child,&status,0,&ru)<0)return 5;
  clock_gettime(CLOCK_MONOTONIC,&end);
  if(!WIFEXITED(status)||WEXITSTATUS(status)!=0)return 6;
  double wall=(end.tv_sec-start.tv_sec)*1000.+(end.tv_nsec-start.tv_nsec)/1e6;
  double cpu=(ru.ru_utime.tv_sec+ru.ru_stime.tv_sec)*1000.+(ru.ru_utime.tv_usec+ru.ru_stime.tv_usec)/1e3;
  printf("%.6f %ld %.6f\n",wall,ru.ru_maxrss,cpu);
}
