package com.wonjun.mentormatch.service;

import com.wonjun.mentormatch.domain.Member;
import com.wonjun.mentormatch.domain.application.Application;
import com.wonjun.mentormatch.domain.post.Post;
import com.wonjun.mentormatch.dto.application.ApplicationResponseDto;
import com.wonjun.mentormatch.dto.application.ApplicationSaveRequestDto;
import com.wonjun.mentormatch.dto.application.ApplicationStatusUpdateRequestDto;
import com.wonjun.mentormatch.exception.ResourceNotFoundException;
import com.wonjun.mentormatch.exception.UnauthorizedException;
import com.wonjun.mentormatch.repository.ApplicationRepository;
import com.wonjun.mentormatch.repository.MemberRepository;
import com.wonjun.mentormatch.repository.PostRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class ApplicationService {

    private final ApplicationRepository applicationRepository;
    private final MemberRepository memberRepository;
    private final PostRepository postRepository;

    @Transactional
    public Long applyToPost(Long menteeId, ApplicationSaveRequestDto requestDto) {
        Member mentee = memberRepository.findById(menteeId)
                .orElseThrow(() -> new ResourceNotFoundException("Mentee not found with id: " + menteeId));
        // TODO: check role is MENTEE

        Post post = postRepository.findById(requestDto.getPostId())
                .orElseThrow(() -> new ResourceNotFoundException("Post not found with id: " + requestDto.getPostId()));
        
        Application application = requestDto.toEntity(post, mentee);
        Application savedApplication = applicationRepository.save(application);
        return savedApplication.getId();
    }

    public List<ApplicationResponseDto> findApplicationsByPost(Long postId, Long memberId) {
        Post post = postRepository.findById(postId)
                .orElseThrow(() -> new ResourceNotFoundException("Post not found with id: " + postId));

        if (!Objects.equals(post.getMember().getId(), memberId)) {
            throw new UnauthorizedException("Only the post's author can view applications.");
        }

        return post.getApplications().stream()
                .map(ApplicationResponseDto::new)
                .collect(Collectors.toList());
    }

    @Transactional
    public void updateApplicationStatus(Long applicationId, Long memberId, ApplicationStatusUpdateRequestDto requestDto) {
        Application application = applicationRepository.findById(applicationId)
                .orElseThrow(() -> new ResourceNotFoundException("Application not found with id: " + applicationId));
        
        Post post = application.getPost();
        if (!Objects.equals(post.getMember().getId(), memberId)) {
            throw new UnauthorizedException("Only the post's author can update application status.");
        }

        application.updateStatus(requestDto.getStatus());
    }
}
