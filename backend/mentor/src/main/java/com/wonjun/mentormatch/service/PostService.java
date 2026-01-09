package com.wonjun.mentormatch.service;

import com.wonjun.mentormatch.domain.Member;
import com.wonjun.mentormatch.domain.post.Post;
import com.wonjun.mentormatch.dto.post.PostResponseDto;
import com.wonjun.mentormatch.dto.post.PostSaveRequestDto;
import com.wonjun.mentormatch.dto.post.PostSimpleResponseDto;
import com.wonjun.mentormatch.dto.post.PostUpdateRequestDto;
import com.wonjun.mentormatch.exception.ResourceNotFoundException;
import com.wonjun.mentormatch.repository.MemberRepository;
import com.wonjun.mentormatch.repository.PostRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class PostService {

    private final PostRepository postRepository;
    private final MemberRepository memberRepository;

    @Transactional
    public Long savePost(Long memberId, PostSaveRequestDto requestDto) {
        Member member = memberRepository.findById(memberId)
                .orElseThrow(() -> new ResourceNotFoundException("Member not found with id: " + memberId));
        // TODO: Add check to ensure member.getRole() is MENTOR

        Post post = requestDto.toEntity(member);
        Post savedPost = postRepository.save(post);
        return savedPost.getId();
    }

    public PostResponseDto findPostById(Long postId) {
        Post post = postRepository.findById(postId)
                .orElseThrow(() -> new ResourceNotFoundException("Post not found with id: " + postId));
        return new PostResponseDto(post);
    }

    public List<PostSimpleResponseDto> findAllPosts() {
        return postRepository.findAll().stream()
                .map(PostSimpleResponseDto::new)
                .collect(Collectors.toList());
    }

    @Transactional
    public void updatePost(Long postId, Long memberId, PostUpdateRequestDto requestDto) {
        Post post = postRepository.findById(postId)
                .orElseThrow(() -> new ResourceNotFoundException("Post not found with id: " + postId));
        
        // TODO: Add authorization check to ensure memberId matches post.getMember().getId()

        post.update(requestDto.getTitle(), requestDto.getContent(), requestDto.getCategory());
    }

    @Transactional
    public void deletePost(Long postId, Long memberId) {
        Post post = postRepository.findById(postId)
                .orElseThrow(() -> new ResourceNotFoundException("Post not found with id: " + postId));

        // TODO: Add authorization check to ensure memberId matches post.getMember().getId()

        postRepository.delete(post);
    }
}
